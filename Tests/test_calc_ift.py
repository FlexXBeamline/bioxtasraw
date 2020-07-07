import os
import shutil

import pytest
import numpy as np

raw_path = os.path.abspath(os.path.join('.', __file__, '..', '..'))
if raw_path not in os.sys.path:
    os.sys.path.append(raw_path)

import bioxtasraw.RAWAPI as raw

def test_ambimeter(gi_gnom_ift):
    score, categories, evaluation = raw.ambimeter(gi_gnom_ift)

    assert score == 0
    assert categories == 1

@pytest.mark.slow
def test_dammif(gi_gnom_ift, temp_directory):

    chi_sq, rg, dmax, mw, excluded_volume = raw.dammif(gi_gnom_ift, 'dammif',
        temp_directory, 'Fast')

    assert os.path.exists(os.path.join(temp_directory, 'dammif-1.pdb'))
    assert os.path.exists(os.path.join(temp_directory, 'dammif.fit'))
    assert os.path.exists(os.path.join(temp_directory, 'dammif.fir'))
    assert os.path.exists(os.path.join(temp_directory, 'dammif.in'))

@pytest.mark.very_slow
def test_dammin(gi_gnom_ift, temp_directory):

    chi_sq, rg, dmax, mw, excluded_volume = raw.dammin(gi_gnom_ift, 'dammin',
        temp_directory, 'Fast')

    assert os.path.exists(os.path.join(temp_directory, 'dammin-0.pdb'))
    assert os.path.exists(os.path.join(temp_directory, 'dammin-1.pdb'))
    assert os.path.exists(os.path.join(temp_directory, 'dammin.fit'))
    assert os.path.exists(os.path.join(temp_directory, 'dammin.fir'))

@pytest.mark.very_slow
def test_damaver(temp_directory):
    fnames = ['glucose_isomerase_{:02d}-1.pdb'.format(i) for i in range(1, 4)]

    for fname in fnames:
        shutil.copy2(os.path.join('./data/dammif_data', fname),
            os.path.join(temp_directory, fname))

    (mean_nsd, stdev_nsd, rep_model, result_dict, res, res_err,
        res_unit) = raw.damaver(fnames, 'damaver', temp_directory)

    assert mean_nsd == 0.443
    assert stdev_nsd == 0.014
    assert res == 25
    assert res_err == 2

@pytest.mark.very_slow
def test_damclust(temp_directory):
    fnames = ['glucose_isomerase_{:02d}-1.pdb'.format(i) for i in range(1, 4)]

    for fname in fnames:
        shutil.copy2(os.path.join('./data/dammif_data', fname),
            os.path.join(temp_directory, fname))

    cluster_list, distance_list = raw.damclust(fnames, 'damaver', temp_directory)

    assert len(cluster_list) == 1
    assert len(distance_list) == 0
    assert float(cluster_list[0].dev) == 0.43326809411161260

@pytest.mark.slow
def test_supcomb(temp_directory):
    shutil.copy2(os.path.join('./data/dammif_data', 'glucose_isomerase_01-1.pdb'),
        os.path.join(temp_directory, 'glucose_isomerase_01-1.pdb'))

    shutil.copy2(os.path.join('./data/dammif_data', '1XIB_4mer.pdb'),
        os.path.join(temp_directory, '1XIB_4mer.pdb'))

    raw.supcomb('glucose_isomerase_01-1.pdb', '1XIB_4mer.pdb', temp_directory)

    assert os.path.exists(os.path.join(temp_directory,
        'glucose_isomerase_01-1_aligned.pdb'))

@pytest.mark.slow
def test_denss(gi_gnom_ift, temp_directory):
    (rho, chi_sq, rg, support_vol, side, q_fit, I_fit, I_extrap,
        err_extrap) = raw.denss(gi_gnom_ift, 'denss', temp_directory, 'Fast',
        seed=1)

    assert os.path.exists(os.path.join(temp_directory, 'denss.mrc'))
    assert os.path.exists(os.path.join(temp_directory, 'denss.log'))
    assert os.path.exists(os.path.join(temp_directory, 'denss_support.mrc'))
    assert os.path.exists(os.path.join(temp_directory, 'denss_map.fit'))
    assert os.path.exists(os.path.join(temp_directory, 'denss_stats_by_step.dat'))
    assert chi_sq == 0.002411384413114013
    assert rg == 38.18223704287973
    assert support_vol == 506818.2928161621
    assert I_fit.sum() == 0.1350911293849589

@pytest.mark.very_slow
def test_denss_average(temp_directory):
    fnames = ['./data/denss_data/glucose_isomerase_{:02d}.mrc'.format(i)
        for i in range(1, 4)]

    for fname in fnames:
        rhos, sides = raw.load_mrc(fnames)

    (average_rho, mean_cor, std_cor, threshold, res, scores,
        fsc) = raw.denss_average(np.array(rhos), sides[0], 'denss',
        temp_directory)

    assert average_rho.sum() == 11.763942082722979
    assert mean_cor == 0.9729911145565486
    assert std_cor == 0.017942342024373233
    assert res == 36.9
    assert os.path.exists(os.path.join(temp_directory, 'denss_average.log'))
    assert os.path.exists(os.path.join(temp_directory, 'denss_fsc.dat'))
    assert os.path.exists(os.path.join(temp_directory, 'denss_average.mrc'))

@pytest.mark.very_slow
def test_denss_align(temp_directory):
    rhos, sides = raw.load_mrc(['./data/denss_data/glucose_isomerase_01.mrc'])

    aligned_density, score = raw.denss_align(rhos[0], sides[0], '1XIB_4mer.pdb',
        './data/dammif_data/', save_datadir=temp_directory)

    assert score == 0.8993042569480916
    assert aligned_density.sum() == 11.784799575805664