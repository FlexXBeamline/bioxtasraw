"""
Created on December 12, 2015

@author: Jesse B. Hopkins

#******************************************************************************
# This file is part of RAW.
#
#    RAW is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    RAW is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with RAW.  If not, see <http://www.gnu.org/licenses/>.
#
#******************************************************************************

The purpose of this module is to contain functions for calculating
values from SAXS profiles. These are intended to be automated
functions, including calculation of rg and molecular weight.

It also contains functions for calling outside packages for use in RAW, like DAMMIF.


"""
import numpy as np
from scipy import integrate as integrate
import os
import time
import subprocess
import scipy.optimize
import wx
import threading
import Queue
import platform
import re
import ast
import logging
import glob
import shutil
import scipy.interpolate
from scipy.constants import Avogadro
from scipy import ndimage
import math
import sys

import SASFileIO
import SASExceptions
import RAWSettings
import RAWCustomCtrl
import RAWGlobals

#Define the rg fit function
def linear_func(x, a, b):
    return a+b*x

def calcRg(q, i, err, transform=True):
    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    error_weight = raw_settings.get('errorWeight')
    if transform:
        #Start out by transforming as usual.
        x = np.square(q)
        y = np.log(i)
        yerr = np.absolute(err/i)
    else:
        x = q
        y = i
        yerr = err

    try:
        if error_weight:
            opt, cov = scipy.optimize.curve_fit(linear_func, x, y, sigma=yerr, absolute_sigma=True)
        else:
            opt, cov = scipy.optimize.curve_fit(linear_func, x, y)
        suc_fit = True
    except TypeError:
        opt = []
        cov = []
        suc_fit = False

    if suc_fit and opt[1] < 0 and np.isreal(opt[1]) and np.isreal(opt[0]):
        RG=np.sqrt(-3.*opt[1])
        I0=np.exp(opt[0])

        #error in rg and i0 is calculated by noting that q(x)+/-Dq has Dq=abs(dq/dx)Dx, where q(x) is your function you're using
        #on the quantity x+/-Dx, with Dq and Dx as the uncertainties and dq/dx the derviative of q with respect to x.
        RGer=np.absolute(0.5*(np.sqrt(-3./opt[1])))*np.sqrt(np.absolute(cov[1,1,]))
        I0er=I0*np.sqrt(np.absolute(cov[0,0]))

    else:
        RG = -1
        I0 = -1
        RGer = -1
        I0er = -1

    return RG, I0, RGer, I0er, opt, cov

def calcRefMW(i0, conc):
    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    ref_mw = raw_settings.get('MWStandardMW')
    ref_I0 = raw_settings.get('MWStandardI0')
    ref_conc = raw_settings.get('MWStandardConc')

    if ref_mw > 0 and ref_I0 > 0 and ref_conc > 0 and conc > 0 and i0 > 0:
            mw = (i0 * (ref_mw/(ref_I0/ref_conc))) / conc
    else:
        mw = -1

    return mw

def calcVpMW(q, i, err, rg, i0, rg_qmin):
    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    density = raw_settings.get('MWVpRho')
    #These functions are used to correct the porod volume for the length of the q vector
    #Coefficients were obtained by direct communication with the authors.
    qc=[0.15, 0.20, 0.25, 0.30, 0.40, 0.45]
    AA=[-9902.46965, -7597.7562, -6869.49936, -5966.34377, -4641.90536, -3786.71549]
    BB=[0.57582, 0.61325, 0.64999, 0.68377, 0.76957, 0.85489]

    fA=scipy.interpolate.interp1d(qc,AA)
    fB=scipy.interpolate.interp1d(qc,BB)

    if q[-1]>0.45:
        A=AA[-1]
        B=BB[-1]
    elif q[-1]<0.15:
        A=AA[0]
        B=BB[0]
    else:
        A=fA(q[-1])
        B=fB(q[-1])

    if i0 > 0:
        #Calculate the Porod Volume
        pVolume = porodVolume(q, i, err, rg, i0, interp = True, rg_qmin=rg_qmin)

        #Correct for the length of the q vector
        pv_cor=(A+B*pVolume)

        mw = pv_cor*density

    else:
        mw = -1
        pVolume = -1
        pv_cor = -1

    return mw, pVolume, pv_cor

def calcAbsMW(i0, conc):
    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    #Default values from Mylonas & Svergun, J. App. Crys. 2007.
    rho_Mprot = raw_settings.get('MWAbsRhoMprot') #e-/g, # electrons per dry mass of protein
    rho_solv = raw_settings.get('MWAbsRhoSolv') #e-/cm^-3, # electrons per volume of aqueous solvent
    nu_bar = raw_settings.get('MWAbsNuBar') #cm^3/g, # partial specific volume of the protein
    r0 = raw_settings.get('MWAbsR0') #cm, scattering lenght of an electron

    d_rho = (rho_Mprot-(rho_solv*nu_bar))*r0
    mw = (Avogadro*i0/conc)/np.square(d_rho)

    return mw



def volumeOfCorrelation(q, i, i0):
    """Calculates the volume of correlation as the ratio of i0 to $\int q*I dq$
    """
    tot=integrate.trapz(q*i,q)
    vc=i0/tot
    return vc

def porodInvariant(q, i,start=0,stop=-1):
    return integrate.trapz(i[start:stop]*np.square(q[start:stop]),q[start:stop])

def porodVolume(q, i, err, rg, i0, start = 0, stop = -1, interp = True, rg_qmin=0):
    if interp and q[0] != 0:
        def f(x):
            return i0*np.exp((-1./3.)*np.square(rg)*np.square(x))

        if rg_qmin>0:

            findClosest = lambda a,l:min(l,key=lambda x:abs(x-a))
            closest_qmin = findClosest(rg_qmin, q)

            idx_min = np.where(q == closest_qmin)[0][0]

            q = q[idx_min:]
            i = i[idx_min:]
            err = err[idx_min:]

        q_interp = np.arange(0,q[0],q[1]-q[0])
        i_interp = f(q_interp)
        err_interp = np.sqrt(i_interp)

        q = np.concatenate((q_interp, q))
        i = np.concatenate((i_interp, i))
        err = np.concatenate((err_interp, err))

    pInvar = porodInvariant(q, i, start, stop)

    pVolume = 2*np.square(np.pi)*i0/pInvar

    return pVolume

def autoRg(sasm, single_fit=False):
    #This function automatically calculates the radius of gyration and scattering intensity at zero angle
    #from a given scattering profile. It roughly follows the method used by the autorg function in the atsas package

    q = sasm.q
    i = sasm.i
    err = sasm.err
    qmin, qmax = sasm.getQrange()

    q = q[qmin:qmax]
    i = i[qmin:qmax]
    err = err[qmin:qmax]

    #Pick the start of the RG fitting range. Note that in autorg, this is done
    #by looking for strong deviations at low q from aggregation or structure factor
    #or instrumental scattering, and ignoring those. This function isn't that advanced
    #so we start at 0.
    data_start = 0

    #Following the atsas package, the end point of our search space is the q value
    #where the intensity has droped by an order of magnitude from the initial value.
    data_end = np.abs(i-i[data_start]/10).argmin()

    #This makes sure we're not getting some weird fluke at the end of the scattering profile.
    if data_end > len(q)/2.:
        found = False
        idx = 0
        while not found:
            idx = idx +1
            if i[idx]<i[0]/10:
                found = True
            elif idx == len(q) -1:
                found = True
        data_end = idx

    #Start out by transforming as usual.
    qs = np.square(q)
    il = np.log(i)
    iler = np.absolute(err/i)

    #Pick a minimum fitting window size. 10 is consistent with atsas autorg.
    min_window = 10

    max_window = data_end-data_start

    fit_list = []

    #It is very time consuming to search every possible window size and every possible starting point.
    #Here we define a subset to search.
    tot_points = max_window
    window_step = tot_points/10
    data_step = tot_points/50

    if window_step == 0:
        window_step =1
    if data_step ==0:
        data_step =1

    window_list = range(min_window,max_window, window_step)
    window_list.append(max_window)


    #This function takes every window size in the window list, stepts it through the data range, and
    #fits it to get the RG and I0. If basic conditions are met, qmin*RG<1 and qmax*RG<1.35, and RG>0.1,
    #We keep the fit.
    for w in window_list:
        for start in range(data_start,data_end-w, data_step):
            x = qs[start:start+w]
            y = il[start:start+w]
            yerr = iler[start:start+w]

            #Remove NaN and Inf values:
            x = x[np.where(np.isnan(y) == False)]
            yerr = yerr[np.where(np.isnan(y) == False)]
            y = y[np.where(np.isnan(y) == False)]

            x = x[np.where(np.isinf(y) == False)]
            yerr = yerr[np.where(np.isinf(y) == False)]
            y = y[np.where(np.isinf(y) == False)]


            RG, I0, RGer, I0er, opt, cov = calcRg(x, y, yerr, transform=False)

            if RG>0.1 and q[start]*RG<1 and q[start+w-1]*RG<1.35 and RGer/RG <= 1:

                a = opt[0]
                b = opt[1]

                r_sqr = 1 - np.square(il[start:start+w]-linear_func(qs[start:start+w], a, b)).sum()/np.square(il[start:start+w]-il[start:start+w].mean()).sum()

                if r_sqr > .15:
                    chi_sqr = np.square((il[start:start+w]-linear_func(qs[start:start+w], a, b))/iler[start:start+w]).sum()

                    #All of my reduced chi_squared values are too small, so I suspect something isn't right with that.
                    #Values less than one tend to indicate either a wrong degree of freedom, or a serious overestimate
                    #of the error bars for the system.
                    dof = w - 2.
                    reduced_chi_sqr = chi_sqr/dof

                    fit_list.append([start, w, q[start], q[start+w-1], RG, RGer, I0, I0er, q[start]*RG, q[start+w-1]*RG, r_sqr, chi_sqr, reduced_chi_sqr])

    #Extreme cases: may need to relax the parameters.
    if len(fit_list)<1:
        #Stuff goes here
        pass

    if len(fit_list)>0:
        fit_list = np.array(fit_list)

        #Now we evaluate the quality of the fits based both on fitting data and on other criteria.

        #Choice of weights is pretty arbitrary. This set seems to yield results similar to the atsas autorg
        #for the few things I've tested.
        qmaxrg_weight = 1
        qminrg_weight = 1
        rg_frac_err_weight = 1
        i0_frac_err_weight = 1
        r_sqr_weight = 4
        reduced_chi_sqr_weight = 0
        window_size_weight = 4

        weights = np.array([qmaxrg_weight, qminrg_weight, rg_frac_err_weight, i0_frac_err_weight, r_sqr_weight,
                            reduced_chi_sqr_weight, window_size_weight])

        quality = np.zeros(len(fit_list))

        max_window_real = float(window_list[-1])

        all_scores = []

        #This iterates through all the fits, and calculates a score. The score is out of 1, 1 being the best, 0 being the worst.
        for a in range(len(fit_list)):
            #Scores all should be 1 based. Reduced chi_square score is not, hence it not being weighted.

            qmaxrg_score = 1-np.absolute((fit_list[a,9]-1.3)/1.3)
            qminrg_score = 1-fit_list[a,8]
            rg_frac_err_score = 1-fit_list[a,5]/fit_list[a,4]
            i0_frac_err_score = 1 - fit_list[a,7]/fit_list[a,6]
            r_sqr_score = fit_list[a,10]
            reduced_chi_sqr_score = 1/fit_list[a,12] #Not right
            window_size_score = fit_list[a,1]/max_window_real

            scores = np.array([qmaxrg_score, qminrg_score, rg_frac_err_score, i0_frac_err_score, r_sqr_score,
                               reduced_chi_sqr_score, window_size_score])

            total_score = (weights*scores).sum()/weights.sum()

            quality[a] = total_score

            all_scores.append(scores)


        #I have picked an aribtrary threshold here. Not sure if 0.6 is a good quality cutoff or not.
        if quality.max() > 0.6:
            # idx = quality.argmax()
            # rg = fit_list[idx,4]
            # rger1 = fit_list[idx,5]
            # i0 = fit_list[idx,6]
            # i0er = fit_list[idx,7]
            # idx_min = fit_list[idx,0]
            # idx_max = fit_list[idx,0]+fit_list[idx,1]

            # try:
            #     #This adds in uncertainty based on the standard deviation of values with high quality scores
            #     #again, the range of the quality score is fairly aribtrary. It should be refined against real
            #     #data at some point.
            #     rger2 = fit_list[:,4][quality>quality[idx]-.1].std()
            #     rger = rger1 + rger2
            # except:
            #     rger = rger1

            if not single_fit:
                try:
                    idx = quality.argmax()
                    rg = fit_list[:,4][quality>quality[idx]-.1].mean()
                    rger = fit_list[:,5][quality>quality[idx]-.1].std()
                    i0 = fit_list[:,6][quality>quality[idx]-.1].mean()
                    i0er = fit_list[:,7][quality>quality[idx]-.1].std()
                    idx_min = int(fit_list[idx,0])
                    idx_max = int(fit_list[idx,0]+fit_list[idx,1]-1)
                except:
                    idx = quality.argmax()
                    rg = fit_list[idx,4]
                    rger = fit_list[idx,5]
                    i0 = fit_list[idx,6]
                    i0er = fit_list[idx,7]
                    idx_min = int(fit_list[idx,0])
                    idx_max = int(fit_list[idx,0]+fit_list[idx,1]-1)
            else:
                idx = quality.argmax()
                rg = fit_list[idx,4]
                rger = fit_list[idx,5]
                i0 = fit_list[idx,6]
                i0er = fit_list[idx,7]
                idx_min = int(fit_list[idx,0])
                idx_max = int(fit_list[idx,0]+fit_list[idx,1]-1)

        else:
            rg = -1
            rger = -1
            i0 = -1
            i0er = -1
            idx_min = -1
            idx_max = -1

    else:
        rg = -1
        rger = -1
        i0 = -1
        i0er = -1
        idx_min = -1
        idx_max = -1
        quality = []
        all_scores = []

    idx_min = idx_min + qmin
    idx_max = idx_max + qmin

    #We could add another function here, if not good quality fits are found, either reiterate through the
    #the data and refit with looser criteria, or accept lower scores, possibly with larger error bars.

    #returns Rg, Rg error, I0, I0 error, the index of the first q point of the fit and the index of the last q point of the fit
    return rg, rger, i0, i0er, idx_min, idx_max


def calcVcMW(sasm, rg, i0, protein = True, interp = True):
    #using the rambo tainer 2013 method for molecular mass.

    raw_settings = wx.FindWindowByName('MainFrame').raw_settings

    q = sasm.q
    i = sasm.i
    err = sasm.err
    qmin, qmax = sasm.getQrange()

    q = q[qmin:qmax]
    i = i[qmin:qmax]
    err = err[qmin:qmax]

    analysis = sasm.getParameter('analysis')

    if interp and q[0] != 0:
        def f(x):
            return i0*np.exp((-1./3.)*np.square(rg)*np.square(x))

        if 'guinier' in analysis:
            guinier_analysis = analysis['guinier']
            qmin = float(guinier_analysis['qStart'])

            findClosest = lambda a,l:min(l,key=lambda x:abs(x-a))
            closest_qmin = findClosest(qmin, q)

            idx_min = np.where(q == closest_qmin)[0][0]

            q = q[idx_min:]
            i = i[idx_min:]
            err = err[idx_min:]

        q_interp = np.arange(0,q[0],q[1]-q[0])
        i_interp = f(q_interp)
        err_interp = np.sqrt(i_interp)

        q = np.concatenate((q_interp, q))
        i = np.concatenate((i_interp, i))
        err = np.concatenate((err_interp, err))

    vc = volumeOfCorrelation(q, i, i0)

    #We then take a ratio of the square of vc to rg
    qr=np.square(vc)/rg

    #The molecular weight is then determined in a power law relationship. Note, the 1000 puts it in kDa

    if protein:
        A = raw_settings.get('MWVcAProtein')
        B = raw_settings.get('MWVcBProtein')
        #For proteins:
        # mw=qr/0.1231/1000
    else:
        A = raw_settings.get('MWVcARna')
        B = raw_settings.get('MWVcBRna')
        #For RNA
        # mw = np.power(qr/0.00934, 0.808)/1000

    mw = (qr/B)**A/1000.

    return mw, np.sqrt(np.absolute(mw)), vc, qr


def getATSASVersion():
    #Checks if we have gnom4 or gnom5
    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        dammifDir = os.path.join(atsasDir, 'dammif.exe')
    else:
        dammifDir = os.path.join(atsasDir, 'dammif')

    if os.path.exists(dammifDir):
        process=subprocess.Popen('%s -v' %(dammifDir), stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True) #gnom4 doesn't do a proper -v!!! So use something else
        output, error = process.communicate()
        output = output.strip()
        error = error.strip()

        dammif_re = 'ATSAS\s*\d+[.]\d+[.]\d*'
        version_match = re.search(dammif_re, output)
        version = version_match.group().split()[-1]

    return version

def runGnom(fname, outname, dmax, args, new_gnom = False):
    #This function runs GNOM from the atsas package. It can do so without writing a GNOM cfg file.
    #It takes as input the filename to run GNOM on, the output name from the GNOM file, the dmax to evaluate
    #at, and a dictionary of arguments, which can be used to set the optional GNOM arguments.
    #Using the GNOM cfg file is significantly faster than catching the interactive input and pass arguments there.

    #Solution for non-blocking reads adapted from stack overflow
    #http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python
    def enqueue_output(out, queue):
        line = 'test'
        line2=''
        while line != '':
            line = out.read(1)
            line2+=line
            if line == ':':
                queue.put_nowait([line2])
                line2=''

        out.close()

    if new_gnom:
        cfg = False
    else:
        cfg = True

    if new_gnom:
        #Check whether everything can be set at the command line:
        fresh_settings = RAWSettings.RawGuiSettings().getAllParams()

        key_ref = { 'gnomExpertFile' : 'expert',
                    'gnomForceRminZero' : 'rmin_zero',
                    'gnomForceRmaxZero' : 'rmax_zero',
                    'gnomNPoints'       : 'npts',
                    'gnomInitialAlpha'  : 'alpha',
                    'gnomAngularScale'  : 'angular',
                    'gnomSystem'        : 'system',
                    'gnomFormFactor'    : 'form',
                    'gnomRadius56'      : 'radius56',
                    'gnomRmin'          : 'rmin',
                    'gnomFWHM'          : 'fwhm',
                    'gnomAH'            : 'ah',
                    'gnomLH'            : 'lh',
                    'gnomAW'            : 'aw',
                    'gnomLW'            : 'lw',
                    'gnomSpot'          : 'spot',
                    'gnomExpt'          : 'expt'
                    }

        cmd_line_keys = {'rmin_zero', 'rmax_zero', 'system', 'rmin', 'radiu56', 'npts', 'alpha'}

        changed = []

        for key in fresh_settings:
            if key.startswith('gnom'):
                if fresh_settings[key][0] != args[key_ref[key]]:
                    changed.append((key_ref[key]))


        if set(changed) <= cmd_line_keys:
            use_cmd_line = True
        else:
            use_cmd_line = False

    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()
    if opsys == 'Windows':
        gnomDir = os.path.join(atsasDir, 'gnom.exe')
    else:
        gnomDir = os.path.join(atsasDir, 'gnom')

    datadir = os.path.dirname(fname)

    if os.path.exists(gnomDir):

        if cfg:
            writeGnomCFG(fname, outname, dmax, args)

            proc = subprocess.Popen('%s' %(gnomDir), shell=True, stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
            proc.communicate('\r\n')

        else:
            if os.path.isfile(os.path.join(datadir, 'gnom.cfg')):
                os.remove(os.path.join(datadir, 'gnom.cfg'))

            if new_gnom and use_cmd_line:
                cmd = '%s --rmax=%s --output=%s --nr=%s' %(gnomDir, str(dmax), outname, str(args['npts']))

                if 'system' in changed:
                    cmd = cmd+' --system=%s' %(str(args['system']))

                if 'rmin' in changed:
                    cmd = cmd+' --rmin=%s' %(str(args['rmin']))

                if 'radius56' in changed:
                    cmd = cmd + ' --rad56=%s' %(str(args['radius56']))

                if 'rmin_zero' in changed:
                    cmd = cmd + ' --force-zero-rmin=%s' %(args['rmin_zero'])

                if 'rmax_zero' in changed:
                    cmd = cmd + ' --force-zero-rmax=%s' %(args['rmax_zero'])

                if 'alpha' in changed:
                    cmd = cmd + ' --alpha=%s' %(str(args['alpha']))

                cmd = cmd + ' %s' %(fname)

                proc = subprocess.Popen(cmd, shell=True, stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)

                output, error = proc.communicate()

            else:

                gnom_q = Queue.Queue()

                proc = subprocess.Popen('%s' %(gnomDir), shell=True, stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
                gnom_t = threading.Thread(target=enqueue_output, args=(proc.stdout, gnom_q))
                gnom_t.daemon = True
                gnom_t.start()

                previous_line = ''
                previous_line2 = ''

                while proc.poll() == None:
                    data = None
                    try:
                        data = gnom_q.get_nowait()
                        data = data[0]
                        gnom_q.task_done()
                    except Queue.Empty:
                        pass

                    if data != None:
                        current_line = data

                        if data.find('[ postscr     ] :') > -1:
                            proc.stdin.write('\r\n') #Printer type, default is postscr

                        elif data.find('Input data') > -1:
                            proc.stdin.write('%s\r\n' %(fname)) #Input data, first file. No default.

                        elif data.find('Output file') > -1:
                            proc.stdin.write('%s\r\n' %(outname)) #Output file, default is gnom.out

                        elif data.find('No of start points to skip') > -1:
                            if 's_skip' in args and args['s_skip'] != '':
                                proc.stdin.write('%s\r\n' %(args['s_skip']))
                            else:
                                proc.stdin.write('\r\n') #Number of start points to skip, default is 0

                        elif data.find('Input data, second file') > -1:
                            proc.stdin.write('\r\n') #Input data, second file, default is none

                        elif data.find('No of end points to omit') > -1:
                            if 'e_skip' in args and args['e_skip'] != '':
                                proc.stdin.write('%s\r\n' %(args['e_skip']))
                            else:
                                proc.stdin.write('\r\n') #Number of end poitns to omit, default is 0

                        elif data.find('Default input errors level') > -1:
                            proc.stdin.write('\r\n') #Default input errors level, default 0.0

                        elif data.find('Angular scale') > -1:
                            if 'angular' in args and args['angular'] != '':
                                proc.stdin.write('%s\r\n' %(args['angular']))
                            else:
                                proc.stdin.write('\r\n') #Angular scale, default 1

                        elif data.find('Plot input data') > -1:
                            proc.stdin.write('n\r\n') #Plot input data, default yes

                        elif data.find('File containing expert parameters') > -1:
                            if 'expert' in args and args['expert'] != '':
                                proc.stdin.write('%s\r\n' %(args['expert']))
                            else:
                                proc.stdin.write('\r\n') #File containing expert parameters, default none

                        elif data.find('Kernel already calculated') > -1:
                            proc.stdin.write('\r\n') #Kernel already calculated, default no

                        elif data.find('Type of system') > -1 or data.find('arbitrary monodisperse)') > -1:
                            if 'system' in args and args['system'] != '':
                                proc.stdin.write('%s\r\n' %(args['system']))
                            else:
                                proc.stdin.write('\r\n') #Type of system, default 0 (P(r) function)

                        elif (data.find('Zero condition at r=rmin') > -1 and data.find('[') > -1) or (previous_line.find('Zero condition at r=rmin') > -1 and previous_line.find('(') > -1):
                            if 'rmin_zero' in args and args['rmin_zero'] != '':
                                proc.stdin.write('%s\r\n' %(args['rmin_zero']))
                            else:
                                proc.stdin.write('\r\n') #Zero condition at r=rmin, default is yes

                        elif (data.find('Zero condition at r=rmax') > -1 and data.find('[') > -1) or (previous_line.find('Zero condition at r=rmax') > -1 and previous_line.find('(') > -1):
                            if 'rmax_zero' in args and args['rmax_zero'] != '':
                                proc.stdin.write('%s\r\n' %(args['rmax_zero']))
                            else:
                                proc.stdin.write('\r\n') #Zero condition at r=rmax, default is yes

                        elif data.find('Rmax for evaluating p(r)') > -1 or data.find('Maximum particle diameter') > -1 or data.find('Maximum characteristic size') > -1 or data.find('Maximum particle thickness') > -1 or data.find('Maximum diameter of particle') > -1 or data.find('Maximum height of cylinder') > -1 or data.find('Maximum outer shell radius') > -1:
                            proc.stdin.write('%s\r\n' %(str(dmax))) #Rmax for evaluating p(r), no default (DMAX!)

                        elif (data.find('Number of points in real space') > -1 and data.find('[') > -1) or previous_line.find('Number of points in real space?') > -1:
                            if 'npts' in args and args['npts'] != -1:
                                proc.stdin.write('%s\r\n' %(str(args['npts'])))
                            else:
                                proc.stdin.write('\r\n') #Number of points in real space, default is 171

                        elif data.find('Kernel-storage file name') > -1:
                            proc.stdin.write('\r\n') #Kernal-storage file name, default is kern.bin

                        elif (data.find('Experimental setup') > -1 and data.find('[') > -1) or data.find('point collimation)') > -1:
                            if 'gnomExp' in args:
                                proc.stdin.write('%s\r\n' %(str(args['gnomExp'])))
                            else:
                                proc.stdin.write('\r\n') #Experimental setup, default is 0 (no smearing)

                        elif data.find('Initial ALPHA') > -1 or previous_line.find('Initial alpha') > -1:
                            if 'alpha' in args and args['alpha'] != 0.0:
                                proc.stdin.write('%s\r\n' %(str(args['alpha'])))
                            else:
                                proc.stdin.write('\r\n') #Initial ALPHA, default is 0.0

                        elif data.find('Plot alpha distribution') > -1:
                            proc.stdin.write('n\r\n') #Plot alpha distribution, default is yes

                        elif data.find('Plot results') > -1:
                            proc.stdin.write('n\r\n') #Plot results, default is no

                        elif data.find('Your choice') > -1:
                            proc.stdin.write('\r\n') #Choice when selecting one of the following options, CR for EXIT

                        elif data.find('Evaluate errors') > -1:
                            proc.stdin.write('\r\n') #Evaluate errors, default yes

                        elif data.find('Plot p(r) with errors') > -1:
                            proc.stdin.write('n\r\n') #Plot p(r) with errors, default yes

                        elif data.find('Next data set') > -1:
                            proc.stdin.write('\r\n') #Next data set, default no

                        elif data.find('Rmin for evaluating p(r)') > -1 or data.find('Minimum characteristic size') > -1 or previous_line.find('Minimum height of cylinder') > -1 or previous_line.find('Minimum outer shell radius') > -1:
                            if 'rmin' in args and args['rmin'] != -1 and args['rmin'] >= 0:
                                proc.stdin.write('%s\r\n' %(str(args['rmin']))) #Rmin, required for some job types
                            else:
                                proc.stdin.write('\r\n' %(str(args['rmin']))) #Default is 0

                        elif data.find('Form factor file for JOB=2') > -1 or data.find('Form Factor file') > -1:
                            proc.stdin.write('%s\r\n' %(str(args['form'])))

                        elif data.find('Cylinder radius') > -1 or data.find('Relative shell thickness') > -1:
                            if 'radius56' in args and args['radius56'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['radius56'])) #Cylinder radius / relative thickness
                            else:
                                proc.stdin.write('\r\n') #Default is 0

                        elif data.find('FWHM for the first run') > 1:
                            #Need something here
                            if 'fwhm' in args and args['fwhm'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['fwhm'])) #Beam FWHM
                            else:
                                proc.stdin.write('\r\n') #Default is 0

                        elif data.find('Slit-height parameter AH') > -1 or previous_line.find('Slit height parameter A') > -1:
                            if 'ah' in args and args['ah'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['ah'])) #Beam height in the detector plane
                            else:
                                proc.stdin.write('\r\n') #Default is 0

                        elif data.find('Slit-height parameter LH') > -1 or previous_line.find('Slit height parameter L') > -1:
                            if 'lh' in args and args['lh'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['lh'])) #Half the height  difference between top and bottom edge of beam in detector plane
                            else:
                                proc.stdin.write('\r\n') #Default is 0

                        elif data.find('parameter AW') > -1 or previous_line.find('Slit width parameter A') > -1:
                            if 'aw' in args and args['aw'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['aw'])) #Projection of beam width in detectgor plane
                            else:
                                proc.stdin.write('\r\n') #Default is 0

                        elif data.find('parameter LW') > -1 or previous_line.find('Slit width parameter L') > -1:
                            if 'lw' in args and args['lw'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['lw'])) #Half of the width difference bewteen top and bottom edge of beam projection in detector plane
                            else:
                                proc.stdin.write('\r\n') #Default is 0

                        elif data.find('Beam profile file') > -1:
                            if 'spot' in args and args['spot'] != -1:
                                proc.stdin.write('%s\r\n') %(str(args['spot'])) #Beam profile file
                            else:
                                proc.stdin.write('\r\n') #Default is none, doesn't use a profile

                        #Prompts from GNOM5
                        elif previous_line.find('(e) expert') > -1:
                            proc.stdin.write('\r\n') #Default is user, good for now. Looks like setting weights is now done in expert mode rather than with a file, so eventually incorporate that.

                        elif previous_line.find('First point to use') > -1:
                            if 's_skip' in args and args['s_skip'] != '':
                                proc.stdin.write('%i\r\n' %(int(args['s_skip'])+1))
                            else:
                                proc.stdin.write('\r\n') #Number of start points to skip, plus one, default is 1

                        elif previous_line.find('Last point to use') > -1:
                            tot_pts = int(current_line.split()[0].strip().rstrip(')'))
                            if 'e_skip' in args and args['e_skip'] != '':
                                proc.stdin.write('%i\r\n' %(tot_pts-int(args['e_skip'])))
                            else:
                                proc.stdin.write('\r\n') #Number of start points to skip, plus one, default is 1

                        #Not implimented yet in RAW.
                        elif previous_line2.find('Slit height setup') > -1:
                            pass

                        elif previous_line2.find('Slight width setup') > -1:
                            pass

                        elif previous_line2.find('Wavelength distribution setup') > -1:
                            pass

                        elif previous_line.find('FWHM of wavelength') > -1:
                            pass

                        elif data.find('Slit height experimental profile file') > -1:
                            pass

                        previous_line2 = previous_line
                        previous_line = current_line
        try:
            iftm=SASFileIO.loadOutFile(outname)[0]
        except IOError:
            raise SASExceptions.GNOMError('No GNOM output file present. GNOM failed to run correctly')

        if cfg:
            try:
                os.remove(os.path.join(datadir, 'gnom.cfg'))
            except Exception as e:
                print e
                print 'GNOM cleanup failed to delete gnom.cfg!'

        if not new_gnom:
            try:
                os.remove(os.path.join(datadir, 'kern.bin'))
            except Exception as e:
                print e
                print 'GNOM cleanup failed to delete kern.bin!'

        return iftm

    else:
        print 'Cannot find ATSAS'
        raise SASExceptions.NoATSASError('Cannot find gnom.')
        return None


def runDatgnom(datname, sasm):
    #This runs the ATSAS package DATGNOM program, to automatically find the Dmax and P(r) function
    #of a scattering profile.
    analysis = sasm.getParameter('analysis')
    if 'guinier' in analysis:
        rg = float(analysis['guinier']['Rg'])
    else:
        rg = -1


    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        datgnomDir = os.path.join(atsasDir, 'datgnom.exe')
    else:
        datgnomDir = os.path.join(atsasDir, 'datgnom')


    if os.path.exists(datgnomDir):

        outname = 't_datgnom.out'
        while os.path.isfile(outname):
            outname = 't'+outname

        version = getATSASVersion()

        if int(version.split('.')[0]) > 2 or (int(version.split('.')[0]) == 2 and int(version.split('.')[1]) >=8):
            new_datgnom = True
        else:
            new_datgnom = False

        if new_datgnom:
            if rg < 0:
                autorg_output = autoRg(sasm)
                rg = autorg_output[0]
                if rg < 0:
                    rg = 20

        if rg <= 0:
            process=subprocess.Popen('%s %s -o %s' %(datgnomDir, datname, outname), stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
        else:
            process=subprocess.Popen('%s %s -o %s -r %f' %(datgnomDir, datname, outname, rg),stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)

        output, error = process.communicate()

        error = error.strip()

        if error == 'Cannot define Dmax' or error=='Could not find Rg' and not new_datgnom:

            if rg <= 0:
                rg, rger, i0, i0er, idx_min, idx_max =autoRg(sasm)
                if rg>10:
                    process=subprocess.Popen('%s %s -o %s -r %f' %(datgnomDir, datname, outname, rg),stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)

                    output, error = process.communicate()
            else:
                process=subprocess.Popen('%s %s -o %s' %(datgnomDir, datname, outname), stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)

                output, error = process.communicate()

        error = error.strip()

        if error == 'Cannot define Dmax' or error=='Could not find Rg' or error=='No intensity values (positive) found' or error == 'LOADATF --E- No data lines recognized.' or error == 'error: rg not specified':
            print 'Unable to run datgnom successfully'
            datgnom_success = False
        # elif error != None:
        #     datgnom_success = False
        else:
            datgnom_success = True

        if datgnom_success:
            iftm=SASFileIO.loadOutFile(outname)[0]
        else:
            iftm = None

        if os.path.isfile(outname):
            try:
                os.remove(outname)
            except Exception, e:
                print e
                print 'DATGNOM cleanup failed to remove the .out file!'

        return iftm

    else:
        print 'Cannot find ATSAS'
        raise SASExceptions.NoATSASError('Cannot find datgnom.')


def writeGnomCFG(fname, outname, dmax, args):
    #This writes the GNOM CFG file, using the arguments passed into the function.
    datadir = os.path.dirname(fname)

    f = open(os.path.join(datadir, 'gnom.cfg'),'w')

    f.write('This line intentionally left blank\n')
    f.write('PRINTER C [      postscr     ]  Printer type\n')
    if 'form' in args and args['form'] != '':
        f.write('FORFAC  C [         %s         ]  Form factor file (valid for JOB=2)\n' %(args['form']))
    else:
        f.write('FORFAC  C [                  ]  Form factor file (valid for JOB=2)\n')
    if 'expert' in args and args['expert'] != '':
        f.write('EXPERT  C [     %s         ]  File containing expert parameters\n' %(args['expert']))
    else:
        f.write('EXPERT  C [     none         ]  File containing expert parameters\n')
    f.write('INPUT1  C [        %s        ]  Input file name (first file)\n' %(fname))
    f.write('INPUT2  C [       none       ]  Input file name (second file)\n')
    f.write('NSKIP1  I [       0         ]  Number of initial points to skip\n')
    f.write('NSKIP2  I [        0         ]  Number of final points to skip\n')
    f.write('OUTPUT  C [       %s         ]  Output file\n' %(outname))
    if 'angular' in args and args['angular'] != 1:
        f.write('ISCALE  I [       %s         ]  Angular scale of input data\n' %(args['angular']))
    else:
        f.write('ISCALE  I [        1         ]  Angular scale of input data\n')
    f.write('PLOINP  C [       n          ]  Plotting flag: input data (Y/N)\n')
    f.write('PLORES  C [       n          ]  Plotting flag: results    (Y/N)\n')
    f.write('EVAERR  C [       y          ]  Error flags: calculate errors   (Y/N)\n')
    f.write('PLOERR  C [       n          ]  Plotting flag: p(r) with errors (Y/N)\n')
    f.write('PLOALPH C [       n          ]  Plotting flag: alpha distribution (Y/N)\n')
    f.write('LKERN   C [       n          ]  Kernel file status (Y/N)\n')
    if 'system' in args and args['system'] != 0:
        f.write('JOBTYP  I [       %s         ]  Type of system (0/1/2/3/4/5/6)\n' %(args['system']))
    else:
        f.write('JOBTYP  I [       0          ]  Type of system (0/1/2/3/4/5/6)\n')
    if 'rmin' in args and args['rmin'] != -1:
        f.write('RMIN    R [        %s         ]  Rmin for evaluating p(r)\n' %(args['rmin']))
    else:
        f.write('RMIN    R [                 ]  Rmin for evaluating p(r)\n')
    f.write('RMAX    R [        %s        ]  Rmax for evaluating p(r)\n' %(str(dmax)))
    if 'rmin_zero' in args and args['rmin_zero'] != '':
        f.write('LZRMIN  C [      %s          ]  Zero condition at r=RMIN (Y/N)\n' %(args['rmin_zero']))
    else:
        f.write('LZRMIN  C [       Y          ]  Zero condition at r=RMIN (Y/N)\n')
    if 'rmax_zero' in args and args['rmax_zero'] != '':
        f.write('LZRMAX  C [      %s          ]  Zero condition at r=RMAX (Y/N)\n' %(args['rmax_zero']))
    else:
        f.write('LZRMAX  C [       Y          ]  Zero condition at r=RMAX (Y/N)\n')
    f.write('KERNEL  C [       kern.bin   ]  Kernel-storage file\n')
    f.write('DEVIAT  R [      0.0         ]  Default input errors level\n')
    f.write('IDET    I [       0          ]  Experimental set up (0/1/2)\n')
    f.write('FWHM1   R [       0.0        ]  FWHM for 1st run\n')
    f.write('FWHM2   R [                  ]  FWHM for 2nd run\n')
    f.write('AH1     R [                  ]  Slit-height parameter AH (first  run)\n')
    f.write('LH1     R [                  ]  Slit-height parameter LH (first  run)\n')
    f.write('AW1     R [                  ]  Slit-width  parameter AW (first  run)\n')
    f.write('LW1     R [                  ]  Slit-width  parameter LW (first  run)\n')
    f.write('AH2     R [                  ]  Slit-height parameter AH (second run)\n')
    f.write('LH2     R [                  ]  Slit-height parameter LH (second run)\n')
    f.write('AW2     R [                  ]  Slit-width  parameter AW (second run)\n')
    f.write('LW2     R [                  ]  Slit-width  parameter LW (second run)\n')
    f.write('SPOT1   C [                  ]  Beam profile file (first run)\n')
    f.write('SPOT2   C [                  ]  Beam profile file (second run)\n')
    if 'alpha' in args and args['alpha'] !=0.0:
        f.write('ALPHA   R [      %s         ]  Initial ALPHA\n' %(str(args['alpha'])))
    else:
        f.write('ALPHA   R [      0.0         ]  Initial ALPHA\n')
    if 'npts' in args and args['npts'] !=101:
        f.write('NREAL   R [       %s        ]  Number of points in real space\n' %(str(args['npts'])))
    else:
        f.write('NREAL   R [       101        ]  Number of points in real space\n')
    f.write('COEF    R [                  ]\n')
    if 'radius56' in args and args['radius56'] != -1:
        f.write('RAD56   R [         %s         ]  Radius/thickness (valid for JOB=5,6)\n' %(args['radius56']))
    else:
        f.write('RAD56   R [                  ]  Radius/thickness (valid for JOB=5,6)\n')
    f.write('NEXTJOB C [        n         ]\n')


    f.close()


def runDammif(fname, prefix, args):
    #Note: This run dammif command must be run with the current working directory as the directory
    #where the file is located. Otherwise, there are issues if the filepath contains a space.

    fname = os.path.split(fname)[1]

    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        dammifDir = os.path.join(atsasDir, 'dammif.exe')
    else:
        dammifDir = os.path.join(atsasDir, 'dammif')


    if os.path.exists(dammifDir):
        if args['mode'].lower() == 'fast' or args['mode'].lower() == 'slow':

            command = '%s --quiet --mode=%s --prefix=%s --unit=%s --symmetry=%s --anisometry=%s' %(dammifDir, args['mode'], prefix, args['unit'], args['sym'], args['anisometry'])
            if args['omitSolvent']:
                command = command + ' --omit-solvent'
            if args['chained']:
                command = command + ' --chained'
            if args['constant'] != '':
                command = command + ' --constant=%s' %(args['constant'])

            command = command + ' %s' %(fname)

            process=subprocess.Popen(command, shell= True)

            return process

        else:
            #Solution for non-blocking reads adapted from stack overflow
            #http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python
            def enqueue_output(out, queue):
                dammifRunning = False
                line = 'test'
                line2=''
                while line != '' and not dammifRunning:
                    line = out.read(1)
                    line2+=line
                    if line == ':':
                        if line2.find('Log opened') > -1:
                            dammifRunning = True
                        queue.put_nowait([line2])
                        line2=''

            dammif_q = Queue.Queue()

            dammifStarted = False

            proc = subprocess.Popen('%s' %(dammifDir), shell = True, stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
            dammif_t = threading.Thread(target=enqueue_output, args=(proc.stdout, dammif_q))
            dammif_t.daemon = True
            dammif_t.start()
            previous_line = ''



            while proc.poll() == None and not dammifStarted:
                data = None
                try:
                    data = dammif_q.get_nowait()
                    data = data[0]
                    dammif_q.task_done()
                except Queue.Empty:
                    pass

                if data != None:
                    current_line = data
                    if data.find('GNOM output file to read?') > -1:
                        proc.stdin.write('%s\r\n' %(fname)) #Dammif input file, no default

                    elif previous_line.find('nanometer') > -1:
                        proc.stdin.write('%s\r\n' %(args['unit'])) #Dammif input file units, default unknown

                    elif previous_line.find('Output file prefix?') > -1:
                        proc.stdin.write('%s\r\n' %(prefix)) #Dammif output file prefix, default dammif

                    elif previous_line.find('Omit output of solvent') > -1:
                        if args['omitSolvent']:
                            proc.stdin.write('%s\r\n' %('no')) #Omit solvent bead output file, default yes
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Create pseudo chains') > -1:
                        if args['chained']:
                            proc.stdin.write('%s\r\n' %('yes')) #Make pseudo chains, default no
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('p1)') > -1:
                        proc.stdin.write('%s\r\n' %(args['sym'])) #Particle symmetry, default P1

                    elif previous_line.find('prolate, (o) oblate') > -1:
                        proc.stdin.write('%s\r\n' %(args['anisometry'])) #Particle anisometry, default Unknown

                    elif data.find('for automatic (default)') > -1:
                        if args['constant'] != '':
                            proc.stdin.write('%s\r\n' %(args['constant'])) #Subtract constant offset, default automatic
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('(s) slow') > -1:
                        proc.stdin.write('i\r\n') #Annealing setup, default slow

                    elif previous_line.find('Maximum bead count') > -1:
                        if args['maxBead'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxBead'])) #Maximum beads to be used, default unlimited
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Dummy atom radius?') > -1:
                        if args['radius'] > -1:
                            proc.stdin.write('%f\r\n' %(args['radius'])) #Dummy atom radius, default 1.0
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Maximum number of spherical harmonics') > -1:
                        if args['harmonics'] > -1:
                            proc.stdin.write('%i\r\n' %(args['harmonics'])) #Maximum number of spherical harmonics to use (1-50), default 20
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Proportion of the curve to be fitted') > -1:
                        if args['propFit'] > -1:
                            proc.stdin.write('%f\r\n' %(args['propFit'])) #Proportion of curve to be fitted, default 1.00
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('emphasised porod)') > -1:
                        if args['curveWeight'] != '':
                            proc.stdin.write('%s\r\n' %(args['curveWeight'])) #Curve weighting function, default emphasised porod
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Initial random seed?') > -1:
                        if args['seed'] != '':
                            proc.stdin.write('%s\r\n' %(args['seed'])) #Initial random seed, default current time
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Maximum number of temperature steps') > -1:
                        if args['maxSteps'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxSteps'])) #Maximum number of temperature steps, default 200
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Minimum number of successes') > -1:
                        if args['minSuccess'] > -1:
                            proc.stdin.write('%i\r\n' %(args['minSuccess'])) #Minimum number of success per temperature step to continue, default 200
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Maximum number of iterations within a single temperature step?') > -1:
                        if args['maxIters'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxIters'])) #Maximum number of iterations per temperature step, default 200000
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('is decreased?') > -1:
                        if args['maxSuccess'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxSuccess'])) #Maximum number of successes per T step, before T is decrease, defaul 20000
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Temperature schedule factor?') > -1:
                        if args['TFactor'] > -1:
                            proc.stdin.write('%f\r\n' %(args['TFactor'])) #Maximum number of successes per T step, before T is decrease, defaul 20000
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Rg penalty weight?') > -1:
                        if args['RgWeight'] > -1:
                            proc.stdin.write('%f\r\n' %(args['RgWeight'])) #Maximum number of successes per T step, before T is decrease, defaul 20000
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Center penalty weight?') > -1:
                        if args['cenWeight'] > -1:
                            proc.stdin.write('%f\r\n' %(args['cenWeight'])) #Maximum number of successes per T step, before T is decrease, defaul 20000
                        else:
                            proc.stdin.write('\r\n')

                    elif previous_line.find('Looseness penalty weight?') > -1:
                        if args['looseWeight'] > -1:
                            proc.stdin.write('%f\r\n' %(args['looseWeight'])) #Maximum number of successes per T step, before T is decrease, defaul 20000
                        else:
                            proc.stdin.write('\r\n')
                    elif data.find('Log opened') > -1:
                        dammifStarted = True

                    previous_line = current_line

            proc.stdout.close()
            proc.stdin.close()

            return proc
    else:
        print 'Cannot find ATSAS'
        raise SASExceptions.NoATSASError('Cannot find dammif.')
        return None


def runDamaver(flist):

    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        damaverDir = os.path.join(atsasDir, 'damaver.exe')
    else:
        damaverDir = os.path.join(atsasDir, 'damaver')


    if os.path.exists(damaverDir):
        command = '%s --automatic' %(damaverDir)

        for item in flist:
            command = command + ' %s' %(item)

        process=subprocess.Popen(command, shell= True, stdout = subprocess.PIPE)

        return process

def runAmbimeter(fname, prefix, args):
    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        ambimeterDir = os.path.join(atsasDir, 'ambimeter.exe')
    else:
        ambimeterDir = os.path.join(atsasDir, 'ambimeter')

    if os.path.exists(ambimeterDir):
        command = '%s --srg=%s --prefix=%s --files=%s %s' %(ambimeterDir, args['sRg'], prefix, args['files'], fname)
        process=subprocess.Popen(command, shell= True, stdout=subprocess.PIPE,stderr=subprocess.PIPE)

        start = time.time()
        while process.poll() == None:
            if time.time()-start > 60:
                raise SASExceptions.NoATSASError('Ambimeter timed out. Try running it from the command line to diagnose this problem.')
                return None

        output, error = process.communicate()

        lines = output.split('\n')
        ambiCats = lines[0].split(':')[-1].strip()
        ambiScore = lines[1].split(':')[-1].strip()
        ambiEval = lines[2]

        return ambiCats, ambiScore, ambiEval

    else:
        print 'Cannot find ATSAS'
        raise SASExceptions.NoATSASError('Cannot find ambimeter.')
        return None

def runDamclust(flist):

    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        damclustDir = os.path.join(atsasDir, 'damclust.exe')
    else:
        damclustDir = os.path.join(atsasDir, 'damclust')


    if os.path.exists(damclustDir):
        command = '%s' %(damclustDir)

        for item in flist:
            command = command + ' %s' %(item)

        process=subprocess.Popen(command, shell= True, stdout = subprocess.PIPE)

        return process


def runDammin(fname, prefix, args):
    #Note: This run dammin command must be run with the current working directory as the directory
    #where the file is located. Otherwise, there are issues if the filepath contains a space.

    fname = os.path.split(fname)[1]

    raw_settings = wx.FindWindowByName('MainFrame').raw_settings
    atsasDir = raw_settings.get('ATSASDir')

    opsys = platform.system()

    if opsys == 'Windows':
        dammifDir = os.path.join(atsasDir, 'dammin.exe')
    else:
        dammifDir = os.path.join(atsasDir, 'dammin')


    if os.path.exists(dammifDir):
        if args['mode'].lower() == 'fast' or args['mode'].lower() == 'slow':

            if args['unit'] == 'Angstrom':
                unit = '1'
            elif args['unit'] == 'Nanometer':
                unit = '2'
            else:
                unit = '1'

            command = '%s --mo=%s --lo=%s --un=%s --sy=%s' %(dammifDir, args['mode'], prefix, unit, args['sym'])

            if args['anisometry'] != 'Unknown':
                command = command + ' --an=%s' %(args['anisometry'])

            command = command + ' %s' %(fname)

            process=subprocess.Popen(command, shell= True, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)

            return process

        else:
            #Solution for non-blocking reads adapted from stack overflow
            #http://stackoverflow.com/questions/375427/non-blocking-read-on-a-subprocess-pipe-in-python
            def enqueue_output(out, queue):
                dammifRunning = False
                line = 'test'
                line2=''
                while line != '' and not dammifRunning:
                    line = out.read(1)
                    line2+=line
                    if line == ':':
                        queue.put_nowait([line2])
                        line2=''
                    elif line == '=':
                        if line2.find('procedure started') > -1:
                            dammifRunning = True
                            queue.put_nowait([line2])
                            line2=''


            dammif_q = Queue.Queue()

            dammifStarted = False

            proc = subprocess.Popen('%s' %(dammifDir), shell = True, stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
            dammif_t = threading.Thread(target=enqueue_output, args=(proc.stdout, dammif_q))
            dammif_t.daemon = True
            dammif_t.start()


            while proc.poll() == None and not dammifStarted:
                data = None
                try:
                    data = dammif_q.get_nowait()
                    data = data[0]
                    dammif_q.task_done()
                except Queue.Empty:
                    pass

                if data is not None:
                    if data.find('[E]xpert') > -1:
                        if args['mode'] == 'Refine':
                            proc.stdin.write('S\r\n') #Dammif run mode
                        else:
                            proc.stdin.write('E\r\n') #Dammif run mode

                    elif data.find('Log file name') > -1:
                        proc.stdin.write('%s\r\n' %(prefix)) #Dammif input file, no default

                    elif data.find('GNOM output file') > -1:
                        proc.stdin.write('%s\r\n' %(fname)) #Dammif input file, no default

                    elif data.find('project description') > -1:
                        proc.stdin.write('\r\n') #Extra information, default is none

                    elif data.find('1/nm') > -1:
                        if args['unit'] == 'Angstrom':
                            proc.stdin.write('1\r\n') #Dammif input file units, default 1/angstrom
                        elif args['unit'] == 'Nanometer':
                            proc.stdin.write('2\r\n') #Dammif input file units, default 1/angstrom
                        else:
                            proc.stdin.write('\r\n') #Dammif input file units, default 1/angstrom

                    elif data.find('Portion of the curve') > -1:
                        if args['propFit'] > -1:
                            proc.stdin.write('%f\r\n' %(args['propFit'])) #Proportion of curve to be fitted, default 1.00
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('parallelepiped') > -1:
                        if 'initialDAM' in args:
                            proc.stdin.write('%s\r\n' %(args['initialDAM'])) #Initial dammin shape, default sphere (S)
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('PICO') > -1:
                        proc.stdin.write('%s\r\n' %(args['sym'])) #Particle symmetry, default P1

                    elif data.find('<P>rolate') > -1:
                        proc.stdin.write('%s\r\n' %(args['anisometry'])) #Particle anisometry, default Unknown

                    elif data.find('knots') > -1 and args['mode'] != 'Refine':
                        if 'knots' in args:
                            proc.stdin.write('%s\r\n' %(str(args['knots']))) #Number of knots in the curve to be fit, default 20
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('automatic subtraction') > -1:
                        if 'damminConstant' in args:
                            proc.stdin.write('%f\r\n' %(args['damminConstant'])) #Subtract constant offset, default automatic
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Maximum order of harmonics') > -1 and args['mode'] != 'Refine':
                        if args['harmonics'] > -1:
                            proc.stdin.write('%i\r\n' %(args['harmonics'])) #Maximum number of spherical harmonics to use (1-50), default 20
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Sphere  diameter [Angstrom]') > -1:
                        if args['diameter'] > -1:
                            proc.stdin.write('%f\r\n' %(args['diameter'])) #Dummy atom diameter, default 1.0
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Packing radius') > -1 and args['mode'] != 'Refine':
                        if args['packing'] > -1:
                            proc.stdin.write('%i\r\n' %(args['packing']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('coordination sphere') > -1 and args['mode'] != 'Refine':
                        if args['coordination'] > -1:
                            proc.stdin.write('%i\r\n' %(args['coordination']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Looseness penalty weight') > -1 and args['mode'] != 'Refine':
                        if args['looseWeight'] > -1:
                            proc.stdin.write('%f\r\n' %(args['looseWeight']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Disconnectivity penalty') > -1 and args['mode'] != 'Refine':
                        if args['disconWeight'] > -1:
                            proc.stdin.write('%i\r\n' %(args['disconWeight']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Peripheral penalty weight') > -1 and args['mode'] != 'Refine':
                        if args['periphWeight'] > -1:
                            proc.stdin.write('%f\r\n' %(args['periphWeight']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Fixing thresholds') > -1 and args['mode'] != 'Refine':
                        proc.stdin.write('\r\n')

                    elif data.find('Randomize the structure') > -1 and args['mode'] != 'Refine':
                        proc.stdin.write('\r\n')

                    elif data.find('0=s^2') > -1 and args['mode'] != 'Refine' and args['mode'] != 'Refine':
                        proc.stdin.write('%s\r\n' %(args['damminCurveWeight'])) #Curve weighting function, default emphasised porod

                    elif data.find('scale factor') > -1 and args['mode'] != 'Refine':
                        proc.stdin.write('\r\n')

                    elif data.find('Initial annealing temperature') > -1 and args['mode'] != 'Refine':
                        proc.stdin.write('\r\n')

                    elif data.find('Annealing schedule factor') > -1 and args['mode'] != 'Refine':
                        if args['annealSched'] > -1:
                            proc.stdin.write('%f\r\n' %(args['annealSched']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('# of independent') > -1 and args['mode'] != 'Refine':
                        proc.stdin.write('\r\n')

                    elif data.find('Max # of iterations') > -1 and args['mode'] != 'Refine':
                        if args['maxIters'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxIters'])) #Maximum number of iterations per temperature step
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Max # of successes') > -1 and args['mode'] != 'Refine':
                        if args['maxSuccess'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxSuccess']))
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Min # of successes') > -1 and args['mode'] != 'Refine':
                        if args['minSuccess'] > -1:
                            proc.stdin.write('%i\r\n' %(args['minSuccess'])) #Minimum number of success per temperature step to continue, default 200
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Max # of annealing steps') > -1 and args['mode'] != 'Refine':
                        if args['maxSteps'] > -1:
                            proc.stdin.write('%i\r\n' %(args['maxSteps'])) #Maximum number of temperature steps, default 200
                        else:
                            proc.stdin.write('\r\n')

                    elif data.find('Reset core') > -1:
                        proc.stdin.write('\r\n')

                    elif data.find('annealing procedure started') > -1:
                        dammifStarted = True

            proc.stdout.close()
            proc.stdin.close()

            return proc
    else:
        print 'Cannot find ATSAS'
        raise SASExceptions.NoATSASError('Cannot find dammif.')
        return None


"""
The following code impliments the pairwise probability test for differences in curves,
known as the CORMAP test. It is taken from the freesas project:
https://github.com/kif/freesas
and used under the MIT license

Information from the original module:
__author__ = "Jerome Kieffer"
__license__ = "MIT"
__copyright__ = "2017, ESRF"
"""

class LongestRunOfHeads(object):
    """Implements the "longest run of heads" by Mark F. Schilling
    The College Mathematics Journal, Vol. 21, No. 3, (1990), pp. 196-207

    See: http://www.maa.org/sites/default/files/pdf/upload_library/22/Polya/07468342.di020742.02p0021g.pdf
    """
    def __init__(self):
        "We store already calculated values for (n,c)"
        self.knowledge = {}

    def A(self, n, c):
        """Calculate A(number_of_toss, length_of_longest_run)

        :param n: number of coin toss in the experiment, an integer
        :param c: length of the longest run of
        :return: The A parameter used in the formula

        """
        if n <= c:
            return 2 ** n
        elif (n, c) in self.knowledge:
            return self.knowledge[(n, c)]
        else:
            s = 0
            for j in range(c, -1, -1):
                s += self.A(n - 1 - j, c)
            self.knowledge[(n, c)] = s
            return s

    def B(self, n, c):
        """Calculate B(number_of_toss, length_of_longest_run)
        to have either a run of Heads either a run of Tails

        :param n: number of coin toss in the experiment, an integer
        :param c: length of the longest run of
        :return: The B parameter used in the formula
        """
        return 2 * self.A(n - 1, c - 1)

    def __call__(self, n, c):
        """Calculate the probability of a longest run of head to occur

        :param n: number of coin toss in the experiment, an integer
        :param c: length of the longest run of heads, an integer
        :return: The probablility of having c subsequent heads in a n toss of fair coin
        """
        if c >= n:
            return 0
        delta = 2 ** n - self.A(n, c)
        if delta <= 0:
            return 0
        return 2.0 ** (np.log2(np.array([delta],dtype=np.float64)) - n)

    def probaB(self, n, c):
        """Calculate the probability of a longest run of head or tails to occur

        :param n: number of coin toss in the experiment, an integer
        :param c: length of the longest run of heads or tails, an integer
        :return: The probablility of having c subsequent heads or tails in a n toss of fair coin
        """

        """Adjust C, because probability calc. is done for a run >
        than c. So in this case, we want to know probability of c, means
        we need to calculate probability of a run of length >c-1
        """
        c=c-1
        if c >= n:
            return 0
        delta = 2**n - self.B(n, c)
        if delta <= 0:
            return 0
        return 2.0**(math.log(delta, 2) - n)

LROH = LongestRunOfHeads()

def cormap_pval(data1, data2):
    """Calculate the probability for a couple of dataset to be equivalent

    Implementation according to:
    http://www.nature.com/nmeth/journal/v12/n5/full/nmeth.3358.html

    :param data1: numpy array
    :param data2: numpy array
    :return: probablility for the 2 data to be equivalent
    """

    if data1.ndim == 2 and data1.shape[1] > 1:
        data1 = data1[:, 1]
    if data2.ndim == 2 and data2.shape[1] > 1:
        data2 = data2[:, 1]

    if data1.shape != data2.shape:
        raise SASExceptions.CorMapError

    diff_data = data2 - data1
    c = measure_longest(diff_data)
    n = diff_data.size

    if c>0:
        prob = LROH.probaB(n, c)
    else:
        prob = 1
    return n, c, round(prob,6)

#This code to find the contiguous regions of the data is based on these
#questions from stack overflow:
#https://stackoverflow.com/questions/4494404/find-large-number-of-consecutive-values-fulfilling-condition-in-a-numpy-array
#https://stackoverflow.com/questions/12427146/combine-two-arrays-and-sort
def contiguous_regions(data):
    """Finds contiguous regions of the difference data. Returns
    a 1D array where each value represents a change in the condition."""

    if np.all(data==0):
        idx = np.array([])
    elif np.all(data>0) or np.all(data<0):
        idx = np.array([0, data.size])
    else:
        condition = data>0
        # Find the indicies of changes in "condition"
        d = np.ediff1d(condition.astype(int))
        idx, = d.nonzero()
        idx = idx+1

        if np.any(data==0):
            condition2 = data<0
            # Find the indicies of changes in "condition"
            d2 = np.ediff1d(condition2.astype(int))
            idx2, = d.nonzero()
            idx2 = idx2+1
            #Combines the two conditions into a sorted array, no need to remove duplicates
            idx = np.concatenate((idx, idx2))
            idx.sort(kind='mergesort')

        #first and last indices are always in this matrix
        idx = np.r_[0, idx]
        idx = np.r_[idx, condition.size]
    return idx

def measure_longest(data):
    """Find the longest consecutive region of positive or negative values"""
    regions = contiguous_regions(data)
    lengths = np.ediff1d(regions)
    if lengths.size > 0:
        max_len = lengths.max()
    else:
        max_len = 0
    return max_len

def run_cormap(sasm_list, correction='None'):
    pvals = np.ones((len(sasm_list), len(sasm_list)))
    corrected_pvals = np.ones_like(pvals)
    failed_comparisons = []

    if correction == 'Bonferroni':
        m_val = sum(range(len(sasm_list)))

    item_data = []

    for index1 in range(len(sasm_list)):
        sasm1 = sasm_list[index1]
        qmin1, qmax1 = sasm1.getQrange()
        i1 = sasm1.i[qmin1:qmax1]
        for index2 in range(1, len(sasm_list[index1:])):
            sasm2 = sasm_list[index1+index2]
            qmin2, qmax2 = sasm2.getQrange()
            i2 = sasm2.i[qmin2:qmax2]

            if np.all(np.round(sasm1.q[qmin1:qmax1], 5) == np.round(sasm2.q[qmin2:qmax2], 5)):
                try:
                    n, c, prob = cormap_pval(i1, i2)
                except SASExceptions.CorMapError:
                    n = 0
                    c = -1
                    prob = -1
                    failed_comparisons.append((sasm1.getParameter('filename'), sasm2.getParameter('filename')))

            else:
                n = 0
                c = -1
                prob = -1
                failed_comparisons.append((sasm1.getParameter('filename'), sasm2.getParameter('filename')))

            pvals[index1, index1+index2] = prob
            pvals[index1+index2, index1] = prob

            if correction == 'Bonferroni':
                c_prob = prob*m_val
                if c_prob > 1:
                    c_prob = 1
                elif c_prob < -1:
                    c_prob = -1
                corrected_pvals[index1, index1+index2] = c_prob
                corrected_pvals[index1+index2, index1] = c_prob

            else:
                c_prob=1

            item_data.append([str(index1), str(index1+index2),
                sasm1.getParameter('filename'), sasm2.getParameter('filename'),
                c, prob, c_prob]
                )

    return item_data, pvals, corrected_pvals, failed_comparisons

def chi2(exp, calc, sig):
    """Return the chi2 discrepancy between experimental and calculated data"""
    return np.sum(np.square(exp - calc) / np.square(sig))

def center_rho(rho, centering="com"):
    """Move electron density map so its center of mass aligns with the center of the grid
    centering - which part of the density to center on. By default, center on the
    center of mass ("com"). Can also center on maximum density value ("max").

    This function is modified from that in the DENSS source code, released here:
    https://github.com/tdgrant1/denss
    That code was released under GPL V3. The original author is Thomas Grant.
    """
    if centering == "max":
        rhocom = np.unravel_index(rho.argmax(), rho.shape)
    else:
        rhocom = np.array(ndimage.measurements.center_of_mass(rho))

    gridcenter = np.array(rho.shape)/2.
    shift = gridcenter-rhocom
    rho = ndimage.interpolation.shift(rho,shift,order=3,mode='wrap')

    return rho

def rho2rg(rho, r, support, dx):
    """Calculate radius of gyration from an electron density map.

    This function is modified from that in the DENSS source code, released here:
    https://github.com/tdgrant1/denss
    That code was released under GPL V3. The original author is Thomas Grant."""

    rhocom = (np.array(ndimage.measurements.center_of_mass(rho))-np.array(rho.shape)/2.)*dx

    rg2 = np.sum(r[support]**2*rho[support])/np.sum(rho[support])
    rg2 = rg2 - np.linalg.norm(rhocom)**2

    rg = np.sign(rg2)*np.abs(rg2)**0.5

    return rg

def denss(q, I, sigq, D, prefix, path, denss_settings, abort_event, denns_queue):
    """Calculates electron density from scattering data.

    This function is modified from that in the DENSS source code, released here:
    https://github.com/tdgrant1/denss
    That code was released under GPL V3. The original author is Thomas Grant."""

    #Get settings
    if denss_settings['electrons'] != '':
        try:
            ne = int(denss_settings['electrons'])
        except Exception:
            ne = None
    else:
        ne = None
    voxel = float(denss_settings['voxel'])
    oversampling = float(denss_settings['oversample'])
    limit_dmax = denss_settings['limitDmax']
    dmax_start_step = int(denss_settings['dmaxStep'])
    recenter = denss_settings['recenter']
    recenter_steps = ast.literal_eval(denss_settings['recenterStep'])
    positivity = denss_settings['positivity']
    extrapolate = denss_settings['extrapolate']
    steps = int(denss_settings['steps'])
    shrinkwrap = denss_settings['shrinkwrap']
    shrinkwrap_sigma_start = float(denss_settings['swSigmaStart'])
    shrinkwrap_sigma_end = float(denss_settings['swSigmaEnd'])
    shrinkwrap_sigma_decay = float(denss_settings['swSigmaDecay'])
    shrinkwrap_threshold_fraction = float(denss_settings['swThresFrac'])
    shrinkwrap_iter = int(denss_settings['swIter'])
    shrinkwrap_minstep = int(denss_settings['swMinStep'])
    chi_end_fraction = float(denss_settings['chiEndFrac'])
    enforce_connectivity = denss_settings['connected']
    enforce_connectivity_steps = ast.literal_eval(denss_settings['conSteps'])
    cutout = denss_settings['cutOutput']
    writeXplor = denss_settings['writeXplor']
    recenter_mode = denss_settings['recenterMode']


    write = True
    write_freq = 100
    seed = None
    file_prefix = os.path.join(path, prefix)

    #Set up a logger
    my_logger = logging.getLogger(prefix)
    my_logger.setLevel(logging.DEBUG)
    my_logger.propagate = False
    my_logger.handlers = []

    my_fh = logging.FileHandler(file_prefix+'.log', mode = 'w')
    my_fh.setLevel(logging.INFO)
    my_fh_formatter = logging.Formatter('%(asctime)s %(message)s', '%Y-%m-%d %I:%M:%S %p')
    my_fh.setFormatter(my_fh_formatter)

    my_sh = RAWCustomCtrl.CustomConsoleHandler(denns_queue)
    my_sh.setLevel(logging.DEBUG)

    my_logger.addHandler(my_fh)
    my_logger.addHandler(my_sh)

    if abort_event.is_set():
        my_logger.info('Aborted!')
        my_fh.close()
        return []

    #Initialize variables
    side = oversampling*D
    halfside = side/2
    n = int(side/voxel)
    #want n to be even for speed/memory optimization with the FFT, ideally a power of 2, but wont enforce that
    if n%2==1:
        n += 1
    nbox = n
    dx = side/n
    dV = dx**3
    V = side**3
    x_ = np.linspace(-halfside, halfside, n)
    x,y,z = np.meshgrid(x_, x_, x_, indexing='ij')
    r = np.sqrt(x**2 + y**2 + z**2)
    df = 1/side

    qx_ = np.fft.fftfreq(x_.size)*n*df*2*np.pi
    qx, qy, qz = np.meshgrid(qx_, qx_, qx_, indexing='ij')
    qr = np.sqrt(qx**2+qy**2+qz**2)
    qmax = np.max(qr)
    qstep = np.min(qr[qr>0])
    nbins = int(qmax/qstep)
    qbins = np.linspace(0,nbins*qstep,nbins+1)
    #create modified qbins and put qbins in center of bin rather than at left edge of bin.
    qbinsc = np.copy(qbins)
    qbinsc += qstep/2.

    #create an array labeling each voxel according to which qbin it belongs
    qbin_labels = np.searchsorted(qbins, qr, 'right')
    qbin_labels -= 1

    #allow for any range of q data
    qdata = qbinsc[np.where( (qbinsc>=q.min()) & (qbinsc<=q.max()) )]
    Idata = np.interp(qdata,q,I)
    if extrapolate:
        qextend = qbinsc[np.where(qbinsc>=qdata.max())]
        Iextend = qextend**-4
        Iextend = Iextend/Iextend[0] * Idata[-1]
        qdata = np.concatenate((qdata,qextend[1:]))
        Idata = np.concatenate((Idata,Iextend[1:]))

    #create list of qbin indices just in region of data for later F scaling
    qbin_args = np.in1d(qbinsc, qdata, assume_unique=True)
    sigqdata = np.interp(qdata, q, sigq)
    Imean = np.zeros((steps+1, len(qbins)))
    chi = np.zeros((steps+1))
    rg = np.zeros((steps+1))
    supportV = np.zeros((steps+1))
    support = np.ones(x.shape, dtype=bool)

    if seed is None:
        #Have to reset the random seed to get a random in different from other processes
        prng = np.random.RandomState()
        seed = prng.randint(2**31-1)
    else:
        seed = int(seed)

    prng = np.random.RandomState(seed)
    rho = prng.random_sample(size=x.shape)

    sigma = shrinkwrap_sigma_start

    #Do some initial logging
    my_logger.info('BEGIN')
    my_logger.info('Output prefix: %s', prefix)
    my_logger.info('Maximum number of steps: %i', steps)
    my_logger.info('q range of input data: %3.3f < q < %3.3f', q.min(), q.max())
    my_logger.info('Maximum dimension: %3.3f', D)
    my_logger.info('Sampling ratio: %3.3f', oversampling)
    my_logger.info('Requested real space voxel size: %3.3f', voxel)
    if ne is not None:
        my_logger.info('Number of electrons: %3.3f', ne)
    else:
        my_logger.info('Number of electrons: ')
    my_logger.info('Limit Dmax: %s', limit_dmax)
    my_logger.info('Recenter: %s', recenter)
    my_logger.info('Positivity: %s', positivity)
    my_logger.info('Extrapolate high q: %s', extrapolate)
    my_logger.info('Shrinkwrap: %s', shrinkwrap)
    my_logger.info('Shrinkwrap sigma start: %s', shrinkwrap_sigma_start)
    my_logger.info('Shrinkwrap sigma end: %s', shrinkwrap_sigma_end)
    my_logger.info('Shrinkwrap sigma decay: %s', shrinkwrap_sigma_decay)
    my_logger.info('Shrinkwrap threshold fraction: %s', shrinkwrap_threshold_fraction)
    my_logger.info('Shrinkwrap iterations: %s', shrinkwrap_iter)
    my_logger.info('Shrinkwrap starting step: %s', shrinkwrap_minstep)
    my_logger.info('Enforce connectivity: %s', enforce_connectivity)
    my_logger.info('Enforce connectivity steps: %s', enforce_connectivity_steps)
    my_logger.info('Chi2 end fraction: %3.3e', chi_end_fraction)
    my_logger.info('Grid size (voxels): %i x %i x %i', n, n, n)
    my_logger.info('Real space box width (angstroms): %3.3f', side)
    my_logger.info('Real space box range (angstroms): %3.3f < x < %3.3f', x_.min(), x_.max())
    my_logger.info('Real space box volume (angstroms^3): %3.3f', V)
    my_logger.info('Real space voxel size (angstroms): %3.3f', dx)
    my_logger.info('Real space voxel volume (angstroms^3): %3.3f', dV)
    my_logger.info('Reciprocal space box width (angstroms^(-1)): %3.3f', qx_.max()-qx_.min())
    my_logger.info('Reciprocal space box range (angstroms^(-1)): %3.3f < qx < %3.3f', qx_.min(), qx_.max())
    my_logger.info('Maximum q vector (diagonal) (angstroms^(-1)): %3.3f', qr.max())
    my_logger.info('Number of q shells: %i', nbins)
    my_logger.info('Width of q shells (angstroms^(-1)): %3.3f', qstep)
    my_logger.info('Random seed: %i', seed)
    my_logger.info('STARTING DENSITY REFINEMENT')

    my_logger.debug("Step  Chi2      Rg      Support Volume")
    my_logger.debug("----- --------- ------- --------------")

    for j in range(steps):
        if abort_event.is_set():
            my_logger.info('Aborted!')
            my_fh.close()
            return []

        F = np.fft.fftn(rho)
        #APPLY RECIPROCAL SPACE RESTRAINTS
        #calculate spherical average of intensities from 3D Fs
        I3D = np.abs(F)**2
        Imean[j] = ndimage.mean(I3D, labels=qbin_labels, index=np.arange(0,qbin_labels.max()+1))

        #scale Fs to match data
        factors = np.ones((len(qbins)))
        factors[qbin_args] = np.sqrt(Idata/Imean[j,qbin_args])
        F *= factors[qbin_labels]
        chi[j] = np.sum(((Imean[j,qbin_args]-Idata)/sigqdata)**2)/qbin_args.size

        #APPLY REAL SPACE RESTRAINTS
        rhoprime = np.fft.ifftn(F, rho.shape)
        rhoprime = rhoprime.real
        if write and j%write_freq == 0:
            SASFileIO.saveDensityXplor(file_prefix+"_current.xplor", rhoprime, side)
        rg[j] = rho2rg(rhoprime, r, support, dx)
        newrho = np.zeros_like(rho)

        #Error Reduction
        newrho[support] = rhoprime[support]
        newrho[~support] = 0.0

        #enforce positivity by making all negative density points zero.
        if positivity:
            netmp = np.sum(newrho)
            newrho[newrho<0] = 0.0
            if np.sum(newrho) != 0:
                newrho *= netmp / np.sum(newrho)

        #update support using shrinkwrap method
        if recenter and j in recenter_steps:
            if recenter_mode == "max":
                rhocom = np.unravel_index(newrho.argmax(), newrho.shape)
            else:
                rhocom = np.array(ndimage.measurements.center_of_mass(newrho))
            gridcenter = np.array(rho.shape)/2.
            shift = gridcenter-rhocom
            shift = shift.astype(int)
            newrho = np.roll(np.roll(np.roll(newrho, shift[0], axis=0), shift[1], axis=1), shift[2], axis=2)
            support = np.roll(np.roll(np.roll(support, shift[0], axis=0), shift[1], axis=1), shift[2], axis=2)

        if shrinkwrap and j >= shrinkwrap_minstep and j%shrinkwrap_iter==0:
            rho_blurred = ndimage.filters.gaussian_filter(newrho, sigma=sigma, mode='wrap')
            support = np.zeros(rho.shape, dtype=bool)
            support[rho_blurred >= shrinkwrap_threshold_fraction*rho_blurred.max()] = True

            if sigma > shrinkwrap_sigma_end:
                sigma = shrinkwrap_sigma_decay*sigma

            if enforce_connectivity and j in enforce_connectivity_steps:
                #label the support into separate segments based on a 3x3x3 grid
                struct = ndimage.generate_binary_structure(3, 3)
                labeled_support, num_features = ndimage.label(support, structure=struct)
                sums = np.zeros((num_features))

                #find the feature with the greatest number of electrons
                for feature in range(num_features):
                    sums[feature-1] = np.sum(newrho[labeled_support==feature])

                big_feature = np.argmax(sums)+1
                #remove features from the support that are not the primary feature
                support[labeled_support != big_feature] = False

        if limit_dmax and j > dmax_start_step:
            support[r>0.6*D] = False

            if np.sum(support) <= 0:
                support = np.ones(rho.shape, dtype=bool)

        supportV[j] = np.sum(support)*dV

        my_logger.debug("% 5i % 4.2e % 3.2f       % 5i          " %(j, chi[j], rg[j], supportV[j]))

        if j > 101 + shrinkwrap_minstep and np.std(chi[j-100:j]) < chi_end_fraction * np.median(chi[j-100:j]):
            rho = newrho
            F = np.fft.fftn(rho)
            break
        else:
            rho = newrho
            F = np.fft.fftn(rho)

    #calculate spherical average intensity from 3D Fs
    Imean[j+1] = ndimage.mean(np.abs(F)**2, labels=qbin_labels, index=np.arange(0, qbin_labels.max()+1))
    chi[j+1] = np.sum(((Imean[j+1,qbin_args]-Idata)/sigqdata)**2)/qbin_args.size

    #scale Fs to match data
    factors = np.ones((len(qbins)))
    factors[qbin_args] = np.sqrt(Idata/Imean[j+1,qbin_args])
    F *= factors[qbin_labels]
    rho = np.fft.ifftn(F, rho.shape)
    rho = rho.real

    #scale total number of electrons
    if ne is not None:
        rho *= ne/np.sum(rho)
        #change rho to be the electron density in e-/angstroms^3, rather
        #than number of electrons,
        #which is what the FFT assumes

    rg[j+1] = rho2rg(rho, r, support, dx)
    supportV[j+1] = supportV[j]

    rho /= dV

    if cutout:
        #here were going to cut rho out of the large real space box
        #to the voxels that contain the particle
        #use D to estimate particle size
        #assume the particle is in the center of the box
        #calculate how many voxels needed to contain particle of size D
        #use bigger than D to make sure we don't crop actual particle in case its larger than expected
        #EMAN2 manual suggests minimum of 1.5, so lets 2 to be safe
        nD = int(2*D/dx)+1
        #make sure final box will still have even samples
        if nD%2==1:
            nD += 1

        min = nbox/2 - nD/2
        max = nbox/2 + nD/2 + 2
        #create new rho array containing only the particle
        newrho = rho[min:max,min:max,min:max]
        rho = newrho
        #do the same for the support
        newsupport = support[min:max,min:max,min:max]
        support = newsupport
        #update side to new size of box
        side = dx * (max-min)

    if write:
        SASFileIO.saveDensityMrc(file_prefix+".mrc", rho, side)
        SASFileIO.saveDensityMrc(file_prefix+"_support.mrc", np.ones_like(rho)*support, side)

        if writeXplor:
            SASFileIO.saveDensityXplor(file_prefix+".xplor", rho, side)
            SASFileIO.saveDensityXplor(file_prefix+"_support.xplor", np.ones_like(rho)*support, side)


        #Write some more output files
        fit = np.zeros(( len(qbinsc),5 ))
        fit[:len(qdata),0] = qdata
        fit[:len(Idata),1] = Idata
        fit[:len(sigqdata),2] = sigqdata
        fit[:len(qbinsc),3] = qbinsc
        fit[:len(Imean[j+1]),4] = Imean[j+1]
        np.savetxt(file_prefix+'_map.fit', fit, delimiter=' ', fmt='%.5e',
            header='q(data),I(data),error(data),q(density),I(density)')

        np.savetxt(file_prefix+'_stats_by_step.txt', np.vstack((chi, rg, supportV)).T, delimiter=" ", fmt="%.5e")

    # #Final output logging and write the log to a file
    my_logger.info('FINISHED DENSITY REFINEMENT')
    my_logger.info('Number of steps: %i', j)
    my_logger.info('Final Chi2: %.3e', chi[j+1])
    my_logger.info('Final Rg: %3.3f', rg[j+1])
    my_logger.info('Final Support Volume: %3.3f', supportV[j+1])
    my_logger.info('END')
    my_fh.close()

    return qdata, Idata, sigqdata, qbinsc, Imean[j+1], chi, rg, supportV

def runDenss(q, I, sigq, D, prefix, path, comm_list, my_lock, thread_num_q,
    wx_queue, abort_event, denss_settings):
    my_lock.acquire()
    my_num = thread_num_q.get()
    den_queue, stop_event = comm_list[int(my_num)-1]
    my_lock.release()

    #Check to see if things have been aborted
    if abort_event.is_set():
        stop_event.set()
        my_lock.acquire()
        wx_queue.put_nowait(['window %s'%(str(my_num)), 'Aborted!\n'])
        wx_queue.put_nowait(['finished', int(my_num)-1])
        my_lock.release()
        return

    den_prefix = prefix+'_%s' %(my_num.zfill(2))

    #Remove old files, so they don't mess up the program
    log_name = den_prefix+'.log'
    xplor_names = [den_prefix+'_current.xplor', den_prefix+'.xplor',
        den_prefix+'_original.xplor', den_prefix+'_precentered.xplor',
        den_prefix+'_support.xplor']
    fit_name = den_prefix+'_map.fit'
    stats_name = den_prefix+'_stats_by_step.txt'
    saxs_name = den_prefix+'_step0_saxs.dat'
    image_names = [den_prefix+'_chis.png', den_prefix+'_fit.png',
        den_prefix+'_rgs.png', den_prefix+'_supportV.png']
    mrc_name = den_prefix+'.mrc'

    names = [log_name, fit_name, stats_name, saxs_name, mrc_name] + xplor_names + image_names

    old_files = [os.path.join(path, name) for name in names]

    for item in old_files:
        if os.path.exists(item):
            os.remove(item)

    #Run DENSS
    my_lock.acquire()
    wx_queue.put_nowait(['status', 'Starting DENSS run %s\n' %(my_num)])
    my_lock.release()

    data = denss(q, I, sigq, D, den_prefix, path, denss_settings,
        abort_event, den_queue)

    stop_event.set()

    if not abort_event.is_set():
        qdata, Idata, sigqdata, qbinsc, Imean, chi, rg, supportV = data
        my_lock.acquire()
        wx_queue.put_nowait(['status', 'Finished run %s\n' %(my_num)])
        my_lock.release()

    my_lock.acquire()
    wx_queue.put_nowait(['finished', int(my_num)-1])
    my_lock.release()

    return data

def runEman2Aver(flist, procs, prefix, path, emanDir):
    #First we stack
    if platform.system() == 'Windows':
        t_dir = os.path.dirname(os.path.dirname(emanDir))
        eman_python = os.path.join(t_dir, 'python.exe')

        my_env = os.environ.copy()
        my_env["PATH"] = (t_dir+';' + os.path.join(t_dir, 'Scripts')+';'
            +emanDir+';'+my_env["PATH"])
    else:
        eman_python = os.path.join(emanDir, 'python')

        my_env = os.environ.copy()
        my_env["PATH"] = emanDir+':'+my_env["PATH"]


    average_py = os.path.join(emanDir, 'e2spt_classaverage.py')

    if os.path.exists(average_py):
        average_cmd = ('%s %s --input %s_stack.hdf --ref %s_reference.hdf '
            '--path %s_aver --parallel thread:%i --saveali --savesteps '
            '--keep 3.0 --keepsig' %(eman_python, average_py, prefix, prefix,
                prefix, procs))

        if len(flist) < 4:
            average_cmd = average_cmd + ' --goldstandardoff'
        process=subprocess.Popen(average_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
        return process
    else:
        return

def runEman2xyz(denss_file, procs, prefix, path, emanDir):
    #First we stack
    if platform.system() == 'Windows':
        t_dir = os.path.dirname(os.path.dirname(emanDir))
        eman_python = os.path.join(t_dir, 'python.exe')

        my_env = os.environ.copy()
        my_env["PATH"] = (t_dir+';' + os.path.join(t_dir, 'Scripts')+';'
            +emanDir+';'+my_env["PATH"])
    else:
        eman_python = os.path.join(emanDir, 'python')

        my_env = os.environ.copy()
        my_env["PATH"] = emanDir+':'+my_env["PATH"]


    xyz_py = os.path.join(RAWGlobals.RAWResourcesDir, 'ali2xyz.py')
    rotate_py = os.path.join(emanDir, 'e2proc3d.py')
    stacks_py = os.path.join(emanDir, 'e2buildstacks.py')

    #First, align the primary file to cardinal axes
    xyz_cmd = '%s %s %s' %(eman_python, xyz_py, denss_file)
    xyz_proc = subprocess.Popen(xyz_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    xyz_output, error = xyz_proc.communicate()

    df_prefix = os.path.splitext(os.path.split(denss_file)[1])[0]
    xyz_file = '%s_ali2xyz.hdf' %(df_prefix)
    xyz_fnp = os.path.splitext(xyz_file)[0]

    #Then we create the set of rotations
    rotx_cmd = ('%s %s %s %s_ali2xyz_x.hdf --process xform.flip:axis=x'
        %(eman_python, rotate_py, xyz_file, df_prefix))
    rotx_proc = subprocess.Popen(rotx_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    rotx_output, error = rotx_proc.communicate()

    roty_cmd = ('%s %s %s %s_ali2xyz_y.hdf --process xform.flip:axis=y'
        %(eman_python, rotate_py, xyz_file, df_prefix))
    roty_proc = subprocess.Popen(roty_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    roty_output, error = roty_proc.communicate()

    rotz_cmd = ('%s %s %s %s_ali2xyz_z.hdf --process xform.flip:axis=z'
        %(eman_python, rotate_py, xyz_file, df_prefix))
    rotz_proc = subprocess.Popen(rotz_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    rotz_output, error = rotz_proc.communicate()

    rotx_file = '%s_x.hdf' %(xyz_fnp)

    rotxy_cmd = ('%s %s %s %s_ali2xyz_xy.hdf --process xform.flip:axis=y'
        %(eman_python, rotate_py, rotx_file, df_prefix))
    rotxy_proc = subprocess.Popen(rotxy_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    rotxy_output, error = rotxy_proc.communicate()

    rotxz_cmd = ('%s %s %s %s_ali2xyz_xz.hdf --process xform.flip:axis=z'
        %(eman_python, rotate_py, rotx_file, df_prefix))
    rotxz_proc = subprocess.Popen(rotxz_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    rotxz_output, error = rotxz_proc.communicate()

    roty_file = '%s_y.hdf' %(xyz_fnp)

    rotyz_cmd = ('%s %s %s %s_ali2xyz_yz.hdf --process xform.flip:axis=z'
        %(eman_python, rotate_py, roty_file, df_prefix))
    rotyz_proc = subprocess.Popen(rotyz_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    rotyz_output, error = rotyz_proc.communicate()

    rotxy_file = '%s_xy.hdf' %(xyz_fnp)

    rotxyz_cmd = ('%s %s %s %s_ali2xyz_xyz.hdf --process xform.flip:axis=z'
        %(eman_python, rotate_py, rotxy_file, df_prefix))
    rotxyz_proc = subprocess.Popen(rotxyz_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    rotxyz_output, error = rotxyz_proc.communicate()

    rot_output = [rotx_output, roty_output, rotz_output, rotxy_output,
        rotxz_output, rotyz_output, rotxyz_output]

    #Then we stack the rotated files into a single stack
    rot_fnames = [xyz_file, rotx_file, roty_file, '%s_z.hdf' %(xyz_fnp), rotxy_file,
        '%s_xz.hdf' %(xyz_fnp), '%s_yz.hdf' %(xyz_fnp), '%s_xyz.hdf' %(xyz_fnp)]

    stack_cmd = '%s %s --stackname %s_xyzstack.hdf' %(eman_python, stacks_py, df_prefix)

    for fname in rot_fnames:
        stack_cmd = stack_cmd + ' %s' %(fname)

    stacks_process = subprocess.Popen(stack_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
    stacks_output, error = stacks_process.communicate()

    return xyz_output, rot_output, stacks_output, rot_fnames

def runEman2Align(denss_file, procs, prefix, path, emanDir):
    if platform.system() == 'Windows':
        t_dir = os.path.dirname(os.path.dirname(emanDir))
        eman_python = os.path.join(t_dir, 'python.exe')

        my_env = os.environ.copy()
        my_env["PATH"] = (t_dir+';' + os.path.join(t_dir, 'Scripts')+';'
            +emanDir+';'+my_env["PATH"])
    else:
        eman_python = os.path.join(emanDir, 'python')

        my_env = os.environ.copy()
        my_env["PATH"] = emanDir+':'+my_env["PATH"]

    align_py = os.path.join(emanDir, 'e2spt_align.py')

    df_prefix = os.path.splitext(os.path.split(denss_file)[1])[0]

    #Then we align the enantiomers in the stack with the reference
    align_dir = os.path.join(path,'%s_enant_ali' %(prefix))
    if os.path.exists(align_dir) and os.path.isdir(align_dir):
        shutil.rmtree(align_dir, ignore_errors=True)

    os.mkdir(align_dir)

    align_cmd = ('%s %s --path=%s --threads %s -v 5 %s_xyzstack.hdf %s_reference.hdf'
        %(eman_python, align_py, align_dir, procs, df_prefix, prefix))

    align_process = subprocess.Popen(align_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)

    return align_process

def runEman2PreAver(flist, procs, prefix, path, emanDir):
    #First we stack
    stacks_py = os.path.join(emanDir, 'e2buildstacks.py')
    if platform.system() == 'Windows':
        t_dir = os.path.dirname(os.path.dirname(emanDir))
        eman_python = os.path.join(t_dir, 'python.exe')

        my_env = os.environ.copy()
        my_env["PATH"] = (t_dir+';' + os.path.join(t_dir, 'Scripts')+';'
            +emanDir+';'+my_env["PATH"])
    else:
        eman_python = os.path.join(emanDir, 'python')

        my_env = os.environ.copy()
        my_env["PATH"] = emanDir+':'+my_env["PATH"]

    if os.path.exists(stacks_py):
        stacks_cmd = '%s %s --stackname %s_stack.hdf' %(eman_python, stacks_py, prefix)

        for item in flist:
            stacks_cmd = stacks_cmd + ' %s' %(item)
        process=subprocess.Popen(stacks_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
        stacks_output, error = process.communicate()
    else:
        return

    #Then we generate a first guess model
    bt_py = os.path.join(emanDir, 'e2spt_binarytree.py')

    if os.path.exists(bt_py):
        bt_cmd = '%s %s --input %s_stack.hdf --path %s_bt_ref --parallel thread:%i' %(eman_python, bt_py, prefix, prefix, procs)
        process=subprocess.Popen(bt_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=path)
        return process, stacks_output
    else:
        return

def runEman2Convert(prefix, path, emanDir):
    if platform.system() == 'Windows':
        t_dir = os.path.dirname(os.path.dirname(emanDir))
        eman_python = os.path.join(t_dir, 'python.exe')

        my_env = os.environ.copy()
        my_env["PATH"] = (t_dir+';' + os.path.join(t_dir, 'Scripts')+';'
            +emanDir+';'+my_env["PATH"])
    else:
        eman_python = os.path.join(emanDir, 'python')

        my_env = os.environ.copy()
        my_env["PATH"] = emanDir+':'+my_env["PATH"]

    convert_py = os.path.join(emanDir, 'e2proc3d.py')

    aver_dir = glob.glob(os.path.join(path, '%s_aver_*' %(prefix)))[-1]

    if os.path.exists(convert_py):
        convert_cmd = '%s %s final_avg_ali2ref.hdf %s_aver.mrc' %(eman_python, convert_py, prefix)

        process=subprocess.Popen(convert_cmd, shell=True, stdout=subprocess.PIPE, env=my_env, cwd=aver_dir)
        stacks_output, error = process.communicate()

        if os.path.exists(os.path.join(path, '%s_avg.mrc' %(prefix))):
            os.remove(os.path.join(path, '%s_avg.mrc' %(prefix)))

        shutil.move(os.path.join(aver_dir, '%s_aver.mrc' %(prefix)), os.path.join(path, '%s_aver.mrc' %(prefix)))

        return stacks_output, error

    else:
        return


