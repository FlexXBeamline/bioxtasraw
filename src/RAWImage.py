'''
Created on Aug 16, 2010

@author: Nielsen

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

'''

import matplotlib, wx, os, cPickle, sys, platform
import numpy as np
from matplotlib.backend_bases import NavigationToolbar2
from matplotlib.backends.backend_wx import NavigationToolbar2Wx
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.widgets import Cursor
import SASImage


RAWWorkDir = sys.path[0]

if os.path.split(sys.path[0])[1] in ['RAW.exe', 'raw.exe']:
    RAWWorkDir = os.path.split(sys.path[0])[0]

class ImagePanelToolbar(NavigationToolbar2Wx):
    ''' The toolbar under the image in the image panel '''
    
    def __init__(self, parent, canvas):

        self.fig_axes = parent.fig.gca()
        self.parent = parent
        
        self._MTB_CIRCLE    = wx.NewId()
        self._MTB_RECTANGLE = wx.NewId()
        self._MTB_POLYGON   = wx.NewId()
        self._MTB_SAVEMASK  = wx.NewId()
        self._MTB_LOADMASK  = wx.NewId()
        self._MTB_CLEAR     = wx.NewId()
        self._MTB_AGBECENT  = wx.NewId()
        self._MTB_HDRINFO   = wx.NewId()
        self._MTB_IMGSET    = wx.NewId()
        
        self.allToolButtons = [self._MTB_CIRCLE, 
                               self._MTB_RECTANGLE,
                               self._MTB_POLYGON,
                               self._MTB_SAVEMASK,
                               self._MTB_LOADMASK,
                               self._MTB_CLEAR,
                 #              self._MTB_AGBECENT,
                               self._MTB_HDRINFO,
                               self._MTB_IMGSET]
        
        NavigationToolbar2Wx.__init__(self, canvas)
         
        workdir = RAWWorkDir
        
        circleIcon    = wx.Bitmap(os.path.join(workdir, "resources", "circle.png"), wx.BITMAP_TYPE_PNG)
        rectangleIcon = wx.Bitmap(os.path.join(workdir, "resources", "rect.png"), wx.BITMAP_TYPE_PNG)
        polygonIcon   = wx.Bitmap(os.path.join(workdir, "resources", "poly.png"), wx.BITMAP_TYPE_PNG)
        saveMaskIcon  = wx.Bitmap(os.path.join(workdir, "resources", "savemask.png"), wx.BITMAP_TYPE_PNG)
        clearIcon     = wx.Bitmap(os.path.join(workdir, "resources", "clear.png"), wx.BITMAP_TYPE_PNG)
        loadMaskIcon  = wx.Bitmap(os.path.join(workdir, "resources", "load.png"), wx.BITMAP_TYPE_PNG)
        #agbeCentIcon  = wx.Bitmap(os.path.join(workdir, "resources", "agbe2.png"), wx.BITMAP_TYPE_PNG)
        hdrInfoIcon   = wx.Bitmap(os.path.join(workdir, "resources", "hdr.png"), wx.BITMAP_TYPE_PNG)
        ImgSetIcon    = wx.Bitmap(os.path.join(workdir, "resources", "imgctrl.png"), wx.BITMAP_TYPE_PNG)
    
        self.AddSeparator()
#        self.AddCheckTool(self._MTB_CIRCLE, circleIcon, shortHelp = 'Create Circle Mask')
#        self.AddCheckTool(self._MTB_RECTANGLE, rectangleIcon, shortHelp = 'Create Rectangle Mask')
#        self.AddCheckTool(self._MTB_POLYGON, polygonIcon, shortHelp = 'Create Polygon Mask')
#        self.AddSeparator()
#        self.AddSimpleTool(self._MTB_SAVEMASK, saveMaskIcon, 'Save Mask')
#        self.AddSimpleTool(self._MTB_LOADMASK, loadMaskIcon, 'Load Mask')
        self.AddSimpleTool(self._MTB_CLEAR, clearIcon, 'Clear Mask')
        #self.AddCheckTool(self._MTB_AGBECENT, agbeCentIcon, shortHelp ='Calibrate using AgBe')
#        self.AddSeparator()
        self.AddSimpleTool(self._MTB_HDRINFO, hdrInfoIcon, 'Show Header Information')
        self.AddSimpleTool(self._MTB_IMGSET, ImgSetIcon, 'Image Display Settings')
    
        self.Bind(wx.EVT_TOOL, self.onCircleTool, id = self._MTB_CIRCLE)
        self.Bind(wx.EVT_TOOL, self.onRectangleTool, id = self._MTB_RECTANGLE)
        self.Bind(wx.EVT_TOOL, self.onPolygonTool, id = self._MTB_POLYGON)
        self.Bind(wx.EVT_TOOL, self.onSaveMaskButton, id = self._MTB_SAVEMASK)
        self.Bind(wx.EVT_TOOL, self.onLoadMaskButton, id = self._MTB_LOADMASK)
        self.Bind(wx.EVT_TOOL, self.onClearButton, id = self._MTB_CLEAR)
        #self.Bind(wx.EVT_TOOL, self.agbeCent, id = self._MTB_AGBECENT)
        self.Bind(wx.EVT_TOOL, self.onHeaderInfoButton, id = self._MTB_HDRINFO)
        self.Bind(wx.EVT_TOOL, self.onImageSettingsButton, id = self._MTB_IMGSET)
    
        self.RemoveTool(self._NTB2_BACK)
        self.RemoveTool(self._NTB2_FORWARD)
        
        self.Realize()
        
        self._current_tool = None
    
    
    def getCurrentTool(self):
        return self._current_tool
    
    def untoggleTool(self):
        self.untoggleAllToolButtons()
    
    def onImageSettingsButton(self, event):
        self.parent.showImageSetDialog()
                
    def onHeaderInfoButton(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()
        self.parent.showHdrInfo()
        
    def agbeCent(self, event):
        self._deactivatePanZoom()
        
        if not self.GetToolState(self._MTB_AGBECENT):
            self.parent.setTool(None)
        else:
            self.parent.setTool('agbecent')
            self.parent.clearPatches()
            self.parent.agbeCalibration()
    
    def onCircleTool(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()    
        self.parent.stopMaskCreation(untoggle = False)
        
        if self.GetToolState(self._MTB_CIRCLE):
            self.untoggleAllToolButtons(self._MTB_CIRCLE)
            self.parent.setTool('circle')
        else:
            self.untoggleAllToolButtons()

    def onRectangleTool(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()
        self.parent.stopMaskCreation(untoggle = False)
        
        if self.GetToolState(self._MTB_RECTANGLE):
            self.untoggleAllToolButtons(self._MTB_RECTANGLE)
            self.parent.setTool('rectangle')
        else:
            self.untoggleAllToolButtons()
    
    def onPolygonTool(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()
        self.parent.stopMaskCreation(untoggle = False)
        
        if self.GetToolState(self._MTB_POLYGON):
            self.untoggleAllToolButtons(self._MTB_POLYGON)
            self.parent.setTool('polygon')
        else:
            self.untoggleAllToolButtons()
        
    def onClearButton(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()
        self.parent.clearAllMasks()

    def onSaveMaskButton(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()
        saveMask()
        
    def onLoadMaskButton(self, event):
        #self._deactivateAgbeCent()
        self._deactivatePanZoom()
        shape = self.parent.img.shape
        
        if shape != None:
            loadMask(shape)

    def untoggleAllToolButtons(self, tog = None):
        for each in self.allToolButtons:
        
            if tog == None:
                self.ToggleTool(each, False)
            elif each != tog:
                self.ToggleTool(each, False)
        
        if tog == None:
            #self._current_tool = None
            self.parent.setTool(None)
    
    def _deactivateMaskTools(self):
        self.untoggleAllToolButtons()
        self.parent.stopMaskCreation()
    
    def _deactivateAgbeCent(self):
        
        if self.GetToolState(self._MTB_AGBECENT):
            self.ToggleTool(self._MTB_AGBECENT, False)
            #self._current_tool = None
            self.parent.setTool(None)
            self.parent.plotStoredMasks()
    
    def _deactivatePanZoom(self):
        ''' Disable the zoon and pan buttons if they are pressed: '''
        if self.GetToolState(self._NTB2_ZOOM):
            self.ToggleTool(self._NTB2_ZOOM, False)
            NavigationToolbar2.zoom(self)
            
        if self.GetToolState(self._NTB2_PAN):
            self.ToggleTool(self._NTB2_PAN, False)
            NavigationToolbar2.pan(self)
    
    ## Overridden functions:
    def zoom(self, *args):
        self._deactivateMaskTools()
        self.ToggleTool(self._NTB2_PAN, False)
        NavigationToolbar2.zoom(self, *args)
    
    def pan(self, *args):
        self._deactivateMaskTools()
        self.ToggleTool(self._NTB2_ZOOM, False)
        NavigationToolbar2.pan(self, *args)
        
class ImagePanel(wx.Panel):
    
    def __init__(self, parent, panel_id, name, *args, **kwargs):
        
        wx.Panel.__init__(self, parent, panel_id, *args, name = name, **kwargs)

        self.fig = matplotlib.figure.Figure((5,4), 75)
        self.canvas = FigureCanvasWxAgg(self, -1, self.fig)
        
        self.canvas.mpl_connect('motion_notify_event', self._onMouseMotion)
        self.canvas.mpl_connect('button_press_event', self._onMouseButtonPressEvent)
        self.canvas.mpl_connect('button_release_event', self._onMouseButtonReleaseEvent)
        self.canvas.mpl_connect('pick_event', self._onPickEvent)
        self.canvas.mpl_connect('key_press_event', self._onKeyPressEvent)
        
        self.toolbar = ImagePanelToolbar(self, self.canvas)
    
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.LEFT|wx.TOP|wx.GROW)
        sizer.Add(self.toolbar, 0, wx.GROW)
        
        #color = parent.GetThemeBackgroundColour()
        #self.SetColor(color)       
        
        self.fig.gca().set_visible(False)
        self.SetSizer(sizer)

        self.img = None
        self.current_sasm = None
        self._canvas_cursor = None
        self._selected_patch = None
        self._first_mouse_pos = None      # Used to keep the mouse position at the same place
                                        # when moving a patch.
                                        
        self.current_tool = None
                                        
        self._polygon_guide_line = None
        self._rectangle_line = None
        self._circle_guide_line = None
        
        self._plotting_in_progress = False
        self._movement_in_progress = False
        self._right_click_on_patch = False
        
        self._chosen_points_x = []
        self._chosen_points_y = []
        self._plotted_patches = []
        self.agbe_selected_points = []
        self.center_patch = None
        
        self.next_mask_number = 0
        
        self.center_click_mode = False
        self.agbe_cent_mode = False
        
        self.plot_parameters = {'axesscale'         : 'linlin', 
                                'storedMasks'       : [],
                                'UpperClim'         : None,
                                'LowerClim'         : None,
                                'ClimLocked'        : False,
                                'ImgScale'          : 'linear',
                                'ColorMap'          : matplotlib.cm.jet,
                                'Brightness'        : 100,
                                'Contrast'          : 100,
                                'maxImgval'         : None,
                                'minImgVal'         : None}
        
        
    def showHdrInfo(self):
        
        if self.current_sasm != None:
            diag = HdrInfoDialog(self, self.current_sasm)
            diag.ShowModal()
            diag.Destroy()
    
    def addLine(self, xpoints, ypoints, color = 'red'):
        
        a = self.fig.gca()
        
        a.add_line(matplotlib.lines.Line2D(xpoints, ypoints, color = color))
        self.canvas.draw()
        
    def setTool(self, tool):
        self.current_tool = tool
        
        if tool in ['circle', 'rectangle', 'polygon']:
            self.toolbar._deactivatePanZoom()
        
    def getTool(self):
        return self.current_tool
    
    def untoggleAllToolButtons(self):
        self.masking_panel = wx.FindWindowByName('MaskingPanel')
        self.masking_panel.disableDrawButtons()
        self.toolbar.untoggleAllToolButtons()
        self.setTool(None)
        
    def showImage(self, img, sasm):
        ''' This function is the one that gets called when a new
        image is to be displayed '''
        
        self.img = np.flipud(img)
                
        self.current_sasm = sasm
        
        self.fig.clear() #Important! or a memory leak will occur!
        
        self._initOnNewImage(img, sasm)
            
        #print "Preparing image for log..."
        # Save zero positions to avoid -inf at 0.0 after log!
        # self.img = uint8((self.img / self.img.max())*255) 
        #self.imgZeros = where(self.img==0.0) 
        
        #if self.plot_parameters['ImgScale'] == 'linear':
        
        a = self.fig.gca()
        
        img_ydim, img_xdim = self.img.shape
        extent = (0, img_xdim, 0, img_ydim)
        self.imgobj = a.imshow(self.img, interpolation = 'nearest', extent = extent)
        
        #else:
        #    self.img[self.imgZeros] = 1
        #    self.imgobj = a.imshow(log(self.img), interpolation = 'nearest', extent = extent)
        #    self.img[self.imgZeros] = 0
        
        self.imgobj.cmap = self.plot_parameters['ColorMap']
        
        a.set_title(sasm.getParameter('filename'))
        a.set_xlabel('x (pixels)')
        a.set_ylabel('y (pixels)')
        a.axis('image')
        
        self.plotStoredMasks()
        
        self.plot_parameters['maxImgVal'] = self.img.max()
        self.plot_parameters['minImgVal'] = self.img.min()
        
        if self.plot_parameters['ClimLocked'] == False:
            clim = self.imgobj.get_clim()

            self.plot_parameters['UpperClim'] = clim[1] 
            self.plot_parameters['LowerClim'] = clim[0]
        else:
            clim = self.imgobj.set_clim(self.plot_parameters['LowerClim'], self.plot_parameters['UpperClim'])
        
        #Update figure:
        self.fig.gca().set_visible(True)
        a.set_xlim(0, img_xdim)
        a.set_ylim(0, img_ydim)
        self.canvas.draw()
        
    def showImageSetDialog(self):
        if self.img != None:
            diag = ImageSettingsDialog(self, self.current_sasm, self.imgobj)
            diag.ShowModal()
            diag.Destroy()
        
    def setPlotParameters(self, new_param):
        self.plot_parameters = new_param
        
    def getPlotParameters(self):
        return self.plot_parameters
    
    def getSelectedAgbePoints(self):
        return self.agbe_selected_points

    def enableCenterClickMode(self, state = True):
        self.center_click_mode = state
    
    def enableAgbeAutoCentMode(self, state = True):
        self.agbe_cent_mode = state
        
#        if state == False:
#            self.agbe_selected_points = []
    
    def _initOnNewImage(self, img, sasm):
        ''' Inserts information about the newly displayed image
        into the plot parameters '''
     
        if not self._canvas_cursor:
            a = self.fig.gca()
            self._canvas_cursor = Cursor(a, useblit=True, color='red', linewidth=1 )
    
    def _onMouseMotion(self, event):
        ''' handles mouse motions, updates the
        status panel with the coordinates and image value and 
        draws the mask guide line.'''
        
        if event.inaxes:
            x, y = event.xdata, event.ydata
           
            mouseX = int(x)
            mouseY = int(y)
        
            try:
                z = self.img[mouseY,mouseX]
            except (IndexError, TypeError):
                z = 0
                
            try:
                mainframe = wx.FindWindowByName('MainFrame')
                mainframe.statusbar.SetStatusText('(x,y) = (' + str(mouseX) + ', ' + str(mouseY) + ')' + '   I = ' + str(z), 1)
                #mainframe.statusbar.SetStatusText('I = ' + str(z), 2)
            except:
                pass
                
            if len(self._chosen_points_x) > 0 and self._plotting_in_progress:
                self._drawMaskGuideLine(mouseX, mouseY)
                
            if self._movement_in_progress == True:                
                self._movePatch(mouseX, mouseY)
                
    def _onMouseButtonPressEvent(self, event):
        ''' Handles matplotlib button press event and splits
        it up into right and left button functions '''
        
        xd, yd = event.xdata, event.ydata
        
        if event.button == 1:    # 1 = Left button
            wx.CallAfter(self._onLeftMouseButtonPress, xd, yd, event)
                  
        if event.button == 3:    # 3 = Right button
            wx.CallAfter(self._onRightMouseButtonPress, xd, yd, event)
            
    def _onMouseButtonReleaseEvent(self, event):
        ''' Handles matplotlib button release event and splits
        it up into right and left button functions '''
        
        xd, yd = event.xdata, event.ydata
        
        if event.button == 1:    # 1 = Left button
            wx.CallAfter(self._onLeftMouseButtonRelease, xd, yd, event)
                  
        if event.button == 3:    # 3 = Right button
            wx.CallAfter(self._onRightMouseButtonRelease, xd, yd, event)
        
    def _onLeftMouseButtonRelease(self, x, y, event):
        
        if self._movement_in_progress == True:
                self._insertNewCoordsIntoMask()
                self._movement_in_progress = False
                self._first_mouse_pos = None

        self._toggleMaskSelection()
        
    def _onLeftMouseButtonPress(self, x, y, event):
        ''' take action on the click based on what tool is
        selected '''
        
        if event.inaxes is None: # If click is outside the canvas area
            return
        
        a = self.fig.gca()
    
        tool = self.getTool()
            
        if tool == 'polygon':
            self._addPolygonPoint(x, y, event)
                
        elif tool == 'circle':
            self._addCirclePoint(x, y, event)
                    
        elif tool == 'rectangle':
            self._addRectanglePoint(x, y, event)
                        
        elif self.agbe_cent_mode == True:
            self.agbe_selected_points.append( (x, y) )
                    
            cir = matplotlib.patches.Circle( (int(x), int(y)), radius = 3, alpha = 1, facecolor = 'yellow', edgecolor = 'yellow')
            a.add_patch(cir)
            self.canvas.draw()
            
        elif self.center_click_mode == True:
            self.center_click_mode = False
            centering_panel = wx.FindWindowByName('CenteringPanel')
            wx.CallAfter(centering_panel.setCenter, [int(x),int(y)])
    
    def _onRightMouseButtonPress(self, x, y, event):
        pass
    
    def _onRightMouseButtonRelease(self, x, y, event):
        
        if self.getTool() == None and self._right_click_on_patch == True:
            self._right_click_on_patch = False
            self._showPopUpMenu()
            
        elif self.getTool() == 'polygon':
            
            if len(self._chosen_points_x) > 2:
                points = []
                for i in range(0, len(self._chosen_points_x)):
                    points.append( (self._chosen_points_x[i], self._chosen_points_y[i]) )
                
                self.plot_parameters['storedMasks'].append( SASImage.PolygonMask(points, self._createNewMaskNumber(), self.img.shape) )
                    
            self.stopMaskCreation()
            self.untoggleAllToolButtons()
    
    def _onKeyPressEvent(self, event):
        
        if event.key == 'escape':
            self.untoggleAllToolButtons()
        
            if self._plotting_in_progress == True:
                self._plotting_in_progress = False
        
            #self.agbeSelectedPoints = []
            self.stopMaskCreation()
            
        if event.key == 'delete' or event.key == 'backspace':
            
            for each in self._plotted_patches:
                if each.selected == 1:
                    
                    for idx in range(0, len(self.plot_parameters['storedMasks'])):
                        if each.id == self.plot_parameters['storedMasks'][idx].getId():
                            self.plot_parameters['storedMasks'].pop(idx)
                            break
            
            self.plotStoredMasks()    
                     
    def _onPickEvent(self, event):
        ''' When a mask(patch) is clicked on, a pick event is thrown.
        This function marks the mask as selected when it
        is picked. 
        
        _onPickEvent and _onLeftMouseButtonRelease are the
        two functions that handles selecting masks.
        '''
        mouseevent = event.mouseevent
        
        if mouseevent.button == 1: #Left click
            self._onPickLeftClick(event)
        elif mouseevent.button == 3: #right click
            self._onPickRightClick(event)
        
    def _onPickLeftClick(self, event):
        ''' when a patch is selected the move flag should be
        set until the mouse button is released
        see _onLeftMouseButtonRelease too. If it is not
        selected it should be. '''
        
        if self.getTool() == None:
                
            self._selected_patch = event.artist
                
            if event.artist.selected == 0:
                event.artist.selected = 1   
            else:
                #If its already selected, set flag
                #to start moving the patch.
                self._movement_in_progress = True
                                
    def _onPickRightClick(self, event):
        ''' If a patch (mask) is selected, then set the
        flag to indicate that a patch has been right clicked 
        on so that a pop up menu is shown when the mouse button is
        released. See _onRightMouseButtonRelease. Otherwise
        select the patch and then set the flag.  '''
         
        self._selected_patch = event.artist 
        event.artist.selected = 1

        self._toggleMaskSelection()
        self._right_click_on_patch = True
        self._selected_patch = event.artist   #toggleMaskSelection sets it to None
            
            
    def _showPopUpMenu(self):
        ''' Show a popup menu that gives the user the
        option to toggle between a positive and negative
        mask. '''
       
        menu = wx.Menu()
        
        i1 = menu.AppendRadioItem(1, 'Normal Mask')
        i2 = menu.AppendRadioItem(2, 'Inverted Mask')
       
        if self._selected_patch.mask.isNegativeMask() == True:
            i2.Check(True)
            
        self.Bind(wx.EVT_MENU, self._onPopupMenuChoice) 
        
        self.PopupMenu(menu)
        
        self._selected_patch = None
        
    def _onPopupMenuChoice(self, evt):
        id = evt.GetId()

        if id == 2:
            self._selected_patch.mask.setAsNegativeMask()     
        else:
            self._selected_patch.mask.setAsPositiveMask()           
            
    #--- ** Mask Creation **
    
    def _getMaskFromId(self, id):
        
        for each in self.plot_parameters['storedMasks']:
            if each.getId() == id:
                return each
    
    def _movePatch(self, mouseX, mouseY):
        patch = self._selected_patch
        
        if patch.get_facecolor() == 'yellow' or patch.get_facecolor() == (1.0, 1.0, 0.0, 0.5):
            
            old_points = self._getMaskFromId(patch.id).getPoints()
            
            x = old_points[0][0]
            y = old_points[0][1]
            
            dX = mouseX - old_points[0][0]
            dY = mouseY - old_points[0][1]
            
            if self._first_mouse_pos == None:        # Is reset when mouse button is released
                self._first_mouse_pos = (dX, dY)
                
            if isinstance(patch, matplotlib.patches.Circle):
                patch.center = (x + dX - self._first_mouse_pos[0], y + dY - self._first_mouse_pos[1])
                 
            elif isinstance(patch, matplotlib.patches.Rectangle):            
                patch.set_x(x + dX - self._first_mouse_pos[0])
                patch.set_y(y + dY - self._first_mouse_pos[1])
                       
            elif isinstance(patch, matplotlib.patches.Polygon):
                new_points = []
                for each in old_points:
                    new_points.append((each[0]+dX - self._first_mouse_pos[0], each[1] + dY - self._first_mouse_pos[1]))
                        
                new_points.append(new_points[0])
                patch.set_xy(new_points)
                        
            self.canvas.draw()
            
    
    def _toggleMaskSelection(self):
        ''' Changes the colour of the patch when the patch is selected
        or deselected. '''
                
        if self._selected_patch != None:
            
            if self._selected_patch.selected == 1:
                self._selected_patch.set_facecolor('yellow')
                    
                id = self._selected_patch.id
                
                for each in self._plotted_patches:
                    if id != each.id:
                        
                        if each.mask.isNegativeMask() == False:
                            each.set_facecolor('red')
                            each.set_edgecolor('red')      
                        else:
                            each.set_facecolor('green')
                            each.set_edgecolor('green')
                        each.selected = 0
                    
                self._selected_patch = None
                self.canvas.draw()
                        
        else:
            for each in self._plotted_patches:
                if each.mask.isNegativeMask() == False:
                    each.set_facecolor('red') 
                    each.set_edgecolor('red')   
                else:
                    each.set_facecolor('green')
                    each.set_edgecolor('green')
                each.selected = 0
            
            self._selected_patch = None
            self.canvas.draw()
    
    def _insertNewCoordsIntoMask(self):
        
        patch = self._selected_patch
        mask = self._getMaskFromId(self._selected_patch.id)
                        
        if isinstance(patch, matplotlib.patches.Circle):
            newCenter = patch.center
            
            #first point is center, next point is first on circle perferie
            mask.setPoints([newCenter, (newCenter[0]+mask.getRadius(), newCenter[1])])
                    
        elif isinstance(patch, matplotlib.patches.Rectangle):
                        
            x = patch.get_x()
            y = patch.get_y()
            
            dx = x - mask.getPoints()[0][0]
            dy = y - mask.getPoints()[0][1]
            
            mask.setPoints([(x, y),(mask.getPoints()[1][0] + dx, mask.getPoints()[1][1] + dy)])
                                
        elif isinstance(patch, matplotlib.patches.Polygon):
            mask.setPoints(patch.get_xy()[:-1])
                              
    def stopMaskCreation(self, untoggle = True):
        
        
        self.untoggleAllToolButtons()
            
        self._chosen_points_x = []
        self._chosen_points_y = []
        self._plotting_in_progress = False
        self._polygon_guide_line = None
        self._circle_guide_line = None
        self._rectangle_line = None
        self.plotStoredMasks()
    
    def clearAllMasks(self):
        
        self.plot_parameters['storedMasks'] = []
        
        a = self.fig.gca()
        
        if a.lines:
            del(a.lines[:])     # delete plotted masks
        if a.patches:
            del(a.patches[:])
        
        self.canvas.draw()
            
    def plotStoredMasks(self):
              
        a = self.fig.gca()        # Get current axis from figure
        stored_masks = self.plot_parameters['storedMasks']
            
        if a.lines:
            del(a.lines[:])     # delete plotted masks
        if a.patches:
            del(a.patches[:])
        
        for each in stored_masks:
            id = wx.NewId()
            each.setId(id)
            
            if each.isNegativeMask() == True:
                col = 'green'
            else:
                col = 'red'
            
            if each.getType() == 'circle':    
                self._drawCircle(each.getPoints(), id, each, color = col)
                
            elif each.getType() == 'rectangle':
                self._drawRectangle(each.getPoints(), id, each, color = col)
                
            elif each.getType() == 'polygon':
                self._drawPolygon(each.getPoints(), id, each, color = col)
                
        
        if self.center_patch and stored_masks:
            a.add_patch(self.center_patch)

        self.canvas.draw()
    
    def drawCenterPatch(self, x, style = 'circle'):
        a = self.fig.gca()
        self.center_patch = matplotlib.patches.Circle( x, radius = 3, alpha = 1, facecolor = 'red', edgecolor = 'red')
        a.add_patch(self.center_patch)
        self.canvas.draw()
        
    def removeCenterPatch(self):
        if self.center_patch:
            try:
                self.center_patch.remove()
            except ValueError:
                pass
            self.center_patch = None
            self.canvas.draw()
    
    def _drawMaskGuideLine(self, x, y):
        ''' Draws the guide lines for the different mask types '''
        
        tool = self.getTool()
        
        a = self.fig.gca()             # Get current axis from figure
        
        if tool == 'circle':
            #if a.lines: del(a.lines[:]) # clear old guide lines
            radius_c = abs(x - self._chosen_points_x[-1])

            circlePoints = SASImage.calcBresenhamCirclePoints(radius_c, self._chosen_points_x[-1], self._chosen_points_y[-1])
            xPoints, yPoints = zip(*circlePoints)
            
            if self._circle_guide_line:
                self.canvas.restore_region(self.background)
                self._circle_guide_line[0].set_ydata(yPoints)
                self._circle_guide_line[0].set_xdata(xPoints)
                
                self.fig.gca().draw_artist(self._circle_guide_line[0])
                self.canvas.blit(self.fig.gca().bbox)
            else:
                self._circle_guide_line = a.plot(xPoints, yPoints, 'r.', animated = True)
                self.canvas.draw()
                self.background = self.canvas.copy_from_bbox(self.fig.gca().bbox)
                        
        elif tool == 'rectangle':
            #if a.lines: del(a.lines[:]) # clear old guide lines
            
            width = x - self._chosen_points_x[-1]
            height = y - self._chosen_points_y[-1]
            
            xPoints = [self._chosen_points_x[-1], x, x, self._chosen_points_x[-1], self._chosen_points_x[-1]]
            yPoints = [self._chosen_points_y[-1], self._chosen_points_y[-1], y, y, self._chosen_points_y[-1]]
            
            if self._rectangle_line:
                self.canvas.restore_region(self.background)
                self._rectangle_line[0].set_ydata(yPoints)
                self._rectangle_line[0].set_xdata(xPoints)
                
                self.fig.gca().draw_artist(self._rectangle_line[0])
                self.canvas.blit(self.fig.gca().bbox)
            else:
                self._rectangle_line = a.plot(xPoints, yPoints, 'r', animated = True)
                self.canvas.draw()
                self.background = self.canvas.copy_from_bbox(self.fig.gca().bbox)


        elif tool == 'polygon':
            xPoint = self._chosen_points_x[-1]
            yPoint = self._chosen_points_y[-1]
            
            if self._polygon_guide_line:
             
                self.canvas.restore_region(self.background)
                self._polygon_guide_line[0].set_ydata([yPoint, y])
                self._polygon_guide_line[0].set_xdata([xPoint, x])
                
                self.fig.gca().draw_artist(self._polygon_guide_line[0])
                self.canvas.blit(self.fig.gca().bbox)

            else:
                self._polygon_guide_line = a.plot([xPoint, x], [yPoint, y], 'r', animated = True)
                self.canvas.draw()
                self.background = self.canvas.copy_from_bbox(self.fig.gca().bbox)

                            
        #self.canvas.draw()
    
    def _drawCircle(self, points, id, mask, color):
        
        a = self.fig.gca()
         
        radius_c = abs(points[1][0] - points[0][0])
        
        cir = matplotlib.patches.Circle( (points[0][0], points[0][1]), color = color, radius = radius_c, alpha = 0.5, picker = True )             
        cir.id = id       # Creating a new parameter called id to distingush them!
        cir.mask = mask
        cir.selected = 0
        self._plotted_patches.append(cir)
        
        a.add_patch(cir)
        
        self._circle_guide_line = None
        
    def _drawRectangle(self, points, id, mask, color):
          
        a = self.fig.gca()
        
        xStart = points[0][0]
        yStart = points[0][1]
        
        xEnd = points[1][0]
        yEnd = points[1][1]

        width = xEnd - xStart
        height = yEnd - yStart
        rect = matplotlib.patches.Rectangle( (xStart, yStart), width, height, color = color, alpha = 0.5, picker = True )
        rect.mask = mask
            
        rect.id = id
        rect.selected = 0
        self._plotted_patches.append(rect)
            
        a.add_patch(rect)
        
        self._rectangle_line = None
        
    def _drawPolygon(self, points, id, mask, color):
    
        a = self.fig.gca()
        
        poly = matplotlib.patches.Polygon( points, alpha = 0.5, picker = True , color = color)
        poly.mask = mask
        a.add_patch(poly)
            
        poly.id = id
        poly.selected = 0
        self._plotted_patches.append(poly)
        
        self._polygon_guide_line = None
        
    def _drawAgBeRings(self, x, r):
        
        a = self.fig.gca()
        
        cir = matplotlib.patches.Circle( x, radius = r, alpha = 1, fill = False, linestyle = 'dashed', linewidth = 1.5, edgecolor = 'red') 
        a.add_patch(cir)
        txt1 = a.text(x[0]-10, x[1]-r-10, 'q = 0.1076', size = 'large', color = 'yellow')
        
        cir = matplotlib.patches.Circle( x, radius = 2*r, alpha = 1, fill = False, linestyle = 'dashed', linewidth = 1.5, edgecolor = 'red') 
        a.add_patch(cir)
        txt2 = a.text(x[0]-10, x[1]-2*r-10, 'q = 0.2152', size = 'large', color = 'yellow')
        
        cir = matplotlib.patches.Circle( x, radius = 3*r, alpha = 1, fill = False, linestyle = 'dashed', edgecolor = 'red') 
        a.add_patch(cir)
        txt3 = a.text(x[0]-10, x[1]-3*r-10, 'q = 0.3229', size = 'large', color = 'yellow')
        
        cir = matplotlib.patches.Circle( x, radius = 4*r, alpha = 1, fill = False, linestyle = 'dashed', edgecolor = 'red') 
        a.add_patch(cir)
        txt4 = a.text(x[0]-10, x[1]-4*r-10, 'q = 0.4305', size = 'large', color = 'yellow')
        
        cir = matplotlib.patches.Circle( x, radius = 3, alpha = 1, facecolor = 'red', edgecolor = 'red')
        a.add_patch(cir)
        
        try:
            self.canvas.draw()
        except ValueError, e:
            print 'ValueError in _drawAgBeRings : ' + str(e)
            
    def _addCirclePoint(self, x, y, event):
        ''' Add point to chosen points list and create a circle
        patch if two points has been chosen '''
        self._plotting_in_progress = True
            
        self._chosen_points_x.append(round(x))
        self._chosen_points_y.append(round(y))
        
        if len(self._chosen_points_x) == 2:
            self.plot_parameters['storedMasks'].append( SASImage.CircleMask(  (self._chosen_points_x[0], self._chosen_points_y[0]),
                                                                              (self._chosen_points_x[1], self._chosen_points_y[1]),
                                                                               self._createNewMaskNumber(), self.img.shape))
            self.untoggleAllToolButtons()
            self.stopMaskCreation()
            
    def _addRectanglePoint(self, x, y, event):
        ''' Add point to chosen points list and create a rectangle
        patch if two points has been chosen '''
        self._plotting_in_progress = True
        
        self._chosen_points_x.append(round(x))
        self._chosen_points_y.append(round(y))
        
        if len(self._chosen_points_x) == 2:
            self.plot_parameters['storedMasks'].append( SASImage.RectangleMask( (self._chosen_points_x[0], self._chosen_points_y[0]),
                                                                                (self._chosen_points_x[1], self._chosen_points_y[1]),
                                                                                 self._createNewMaskNumber(), self.img.shape ))                                        
            self.untoggleAllToolButtons()
            self.stopMaskCreation()
    
    def _addPolygonPoint(self, x, y, event):
        ''' Add points to the polygon and draw lines
        between points if enough points are present '''

        if len(self._chosen_points_x) > 0:
            if event.inaxes is not None:
                        
                new_line_x = [self._chosen_points_x[-1], round(x)]
                new_line_y = [self._chosen_points_y[-1], round(y)]
                    
                self._chosen_points_x.append(round(x))
                self._chosen_points_y.append(round(y))

                if len(self._chosen_points_x) >= 2:
                    self.fig.gca().plot(new_line_x, new_line_y,'r')
                    self.canvas.draw()
                    
                    #update blitz background region for guideline: 
                    self.background = self.canvas.copy_from_bbox(self.fig.gca().bbox)
        else:
            self._chosen_points_x.append(round(x))
            self._chosen_points_y.append(round(y))
            self._plotting_in_progress = True
    
    def _createNewMaskNumber(self):
        
        storedMasks = self.plot_parameters['storedMasks']
        
        if not(storedMasks):
            self.next_mask_number = 0
        else:
            self.next_mask_number = self.next_mask_number + 1

        return self.next_mask_number
    
    def showCenter(self):
        pass
    
    def _drawCenter(self):
        self.fig.gca()
        
    def clearPatches(self):
        a = self.fig.gca()
         
        if a.lines:
            del(a.lines[:])     # delete plotted masks
        if a.patches:
            del(a.patches[:])
        if a.texts:
            del(a.texts[:])
              
        self.canvas.draw()
        
    def clearFigure(self):
        self.fig.clear()
        self.fig.gca().set_visible(False)
        self.canvas.draw()
        
    def updateClim(self):
        
        upper = self.plot_parameters['UpperClim']
        lower = self.plot_parameters['LowerClim']
        
        if upper != None and lower != None and self.imgobj != None:
            if lower < upper:
                self.imgobj.set_clim(lower, upper)
                self.canvas.draw()
            
    def updateImage(self):
        self.canvas.draw()
    
class HdrInfoDialog(wx.Dialog):
    
    def __init__(self, parent, sasm):
        
        wx.Dialog.__init__(self, parent, -1, size = (500,500))

        self.sasm = sasm
        
        final_sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = self.createHdrInfoWindow()
        
        final_sizer.Add(sizer, 1, wx.EXPAND)
        
        self.SetSizer(final_sizer)
        
        self.CenterOnParent()
        
    def createHdrInfoWindow(self):
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.text = wx.TextCtrl(self, -1, style = wx.TE_MULTILINE)
        
        self.text.AppendText('#############################################\n')
        self.text.AppendText('                                 Header information\n')
        self.text.AppendText('#############################################\n\n')
        
        
        if self.sasm != None:
            param = self.sasm.getAllParameters()
            keys = param.iterkeys()
        
            for each in keys:
                
                if each == 'imageHeader':
                    imghdr = param[each]
                    imghdr_keys = sorted(imghdr.keys())
                    self.text.AppendText(str(each) + ' : \n')
                    for eachkey in imghdr_keys:
                        self.text.AppendText(str(eachkey) + ' : ' + str(imghdr[eachkey])+'\n')
                    
                else:
                    self.text.AppendText(str(each) + ' : ' + str(param[each])+'\n')
        
        sizer.Add(self.text, 1, wx.EXPAND)
        
        return sizer
    

def createMaskFileDialog(mode):
        
        file = None
        
        if mode == wx.OPEN:
            filters = 'Mask files (*.msk)|*.msk|All files (*.*)|*.*'
            dialog = wx.FileDialog( None, style = mode, wildcard = filters)
        if mode == wx.SAVE:
            filters = 'Mask files (*.msk)|*.msk'
            dialog = wx.FileDialog( None, style = mode | wx.OVERWRITE_PROMPT, wildcard = filters)        
        
        # Show the dialog and get user input
        if dialog.ShowModal() == wx.ID_OK:
            file = dialog.GetPath()
            
        # Destroy the dialog
        dialog.Destroy()
        
        return file
    
def loadMask(img_dim):
        
        file = createMaskFileDialog(wx.OPEN)
        
        if file:     
            answer = wx.MessageBox('Do you want set this mask as the current "Beam Stop" mask?', 'Use as beamstop mask?', wx.YES_NO | wx.ICON_QUESTION)
            
            if answer == wx.YES:
                main_frame = wx.FindWindowByName('MainFrame')
                queue = main_frame.getWorkerThreadQueue()
                queue.put(['load_mask', [file, img_dim, 'BeamStopMask']])
                
            elif answer == wx.NO:
                answer = wx.MessageBox('Do you want set this mask as the current "Readout noise" mask?', 'Use as readout noise mask?', wx.YES_NO | wx.ICON_QUESTION)
                
                if answer == wx.YES:
                    main_frame = wx.FindWindowByName('MainFrame')
                    queue = main_frame.getWorkerThreadQueue()
                    queue.put(['load_mask', [file, img_dim, 'ReadOutNoiseMask']])
            
def saveMask():
        
        img_panel = wx.FindWindowByName('ImagePanel')
        plot_parameters = img_panel.getPlotParameters()    
        
        masks = plot_parameters['storedMasks']
        img_dim = img_panel.img.shape
        
        if masks != []:
           
            file = createMaskFileDialog(wx.SAVE)
            
            if file:
                main_frame = wx.FindWindowByName('MainFrame')
                queue = main_frame.getWorkerThreadQueue()
                queue.put(['save_mask', [file, masks]])             
        else:
             wx.MessageBox('You need to create a mask before you can save it!', 'No mask to save!', wx.OK)
             
def showUseMaskDialog(file, img_dim):
    
    answer = wx.MessageBox('Do you want set this mask as the current "Beam Stop" mask?', 'Use as beamstop mask?', wx.YES_NO | wx.ICON_QUESTION)
        
    if answer == wx.NO:
        answer = wx.MessageBox('Do you want set this mask as the current "Readout noise" mask?', 'Use as readout noise mask?', wx.YES_NO | wx.ICON_QUESTION)
                    
        if answer == wx.YES:
            main_frame = wx.FindWindowByName('MainFrame')
            queue = main_frame.getWorkerThreadQueue()
            queue.put(['load_mask', [file, img_dim, 'ReadOutNoiseMask']])
    else:
        main_frame = wx.FindWindowByName('MainFrame')
        queue = main_frame.getWorkerThreadQueue()
        queue.put(['load_mask', [file, img_dim, 'BeamStopMask']])


        
             

class ImageSettingsDialog(wx.Dialog):

    def __init__(self, parent, sasm, ImgObj):
        
        wx.Dialog.__init__(self, parent, -1, title = 'Image Display Settings')

        self.sasm = sasm
        self.ImgObj = ImgObj
        self.parent = parent
        
        self.newImg = self.parent.img.copy()
        
        sizer = wx.BoxSizer(wx.VERTICAL)
  
        if not parent.plot_parameters['UpperClim'] == None and not parent.plot_parameters['LowerClim'] == None:
            self.maxval = parent.plot_parameters['maxImgVal']
            self.minval = parent.plot_parameters['minImgVal']
        else:
            self.maxval = 100
            self.minval = 0
        
        self.sliderinfo = (                           
                           ################### ctrl,     slider #############
                           ('Upper limit:', wx.NewId(), wx.NewId(), 'UpperClim'),
                           ('Lower limit:', wx.NewId(), wx.NewId(), 'LowerClim'),
                           ('Brightness:', wx.NewId(), wx.NewId(), 'Brightness'))
                          
        
        self.scaleinfo = (('Linear', wx.NewId(), 'ImgScale'), 
                          ('Logarithmic', wx.NewId(), 'ImgScale'))
        
        
        box = wx.StaticBox(self, -1, 'Image parameters')
        finalfinal_sizer = wx.BoxSizer()
        
        slidersizer = self.createSettingsWindow()
        scalesizer = self.createScaleSelector()
        colormapsizer = self.createColormapSelector()
        
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        sizer.Add(slidersizer, 1, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)
        
        self.okButton = wx.Button(self, -1, 'OK')
        self.okButton.Bind(wx.EVT_BUTTON, self.OnOk)
        
        finalSizer = wx.BoxSizer(wx.VERTICAL)
        finalSizer.Add(sizer, 0, wx.EXPAND, wx.TOP | wx.LEFT | wx.RIGHT, 5)
        finalSizer.Add(scalesizer,0, wx.EXPAND, wx.LEFT | wx.RIGHT, 5)
        finalSizer.Add(colormapsizer,0, wx.EXPAND, wx.LEFT | wx.RIGHT, 5)
        finalSizer.Add(self.okButton, 0, wx.CENTER | wx.TOP, 10)
        
        finalfinal_sizer.Add(finalSizer, 0, wx.ALL, 10)
        
        self.SetSizer(finalfinal_sizer)
        self.Fit()
        
        try:
            file_list_ctrl = wx.FindWindowByName('FilePanel')
            pos = file_list_ctrl.GetScreenPosition()
            self.MoveXY(pos[0], pos[1])
        except:
            pass
        
    def OnOk(self, event):
        
        self.EndModal(1)
        
    def createColormapSelector(self):
        
        sizer = wx.BoxSizer()
        
        self.colorRadioList = ['Gray', 'Heat', 'Rainbow', 'Jet', 'Spectral']
        
        self.colormaps = [matplotlib.cm.gray,
                          matplotlib.cm.gist_heat,
                          matplotlib.cm.gist_rainbow,
                          matplotlib.cm.jet,
                          matplotlib.cm.spectral]
        
        rb = wx.RadioBox(self, label="Colormaps", choices=self.colorRadioList, style=wx.RA_SPECIFY_COLS)
        rb.Bind(wx.EVT_RADIOBOX, self.onColorMapsRadioBox)

        rb.SetSelection(self.colormaps.index(self.parent.plot_parameters['ColorMap']))
        
        sizer.Add(rb,1,wx.EXPAND)
        
        return sizer
    
    def onColorMapsRadioBox(self, event):
        
        selection = event.GetSelection()
                
        if self.colorRadioList[selection] == 'Gray':
            self.parent.plot_parameters['ColorMap'] = matplotlib.cm.gray
        elif self.colorRadioList[selection] == 'Heat':
            self.parent.plot_parameters['ColorMap'] = matplotlib.cm.gist_heat
        elif self.colorRadioList[selection] == 'Rainbow':
            self.parent.plot_parameters['ColorMap'] = matplotlib.cm.gist_rainbow
        elif self.colorRadioList[selection] == 'Jet':
            self.parent.plot_parameters['ColorMap'] = matplotlib.cm.jet
        elif self.colorRadioList[selection] == 'Bone':
            self.parent.plot_parameters['ColorMap'] = matplotlib.cm.bone
        elif self.colorRadioList[selection] == 'Spectral':
            self.parent.plot_parameters['ColorMap'] = matplotlib.cm.spectral
        
        if self.ImgObj != None:
            self.ImgObj.cmap = self.parent.plot_parameters['ColorMap']
            self.ImgObj.changed()
            self.parent.updateImage()
        
    def createScaleSelector(self):
        
        sizer = wx.BoxSizer()
        
        radioList = ['Linear', 'Logarithmic']
        rb = wx.RadioBox(self, label="Image scaling", choices=radioList, style=wx.RA_SPECIFY_COLS)
        rb.Bind(wx.EVT_RADIOBOX, self.onRadioBox)

        if self.parent.plot_parameters['ImgScale'] == 'linear':
            rb.SetSelection(0)
        else:
            rb.SetSelection(1)
            
        ## Disabled for now:
        rb.Enable(False)

        sizer.Add(rb,1,wx.EXPAND)
        
        return sizer
    
    def onRadioBox(self, event):
        
        selection = event.GetSelection()
        
        if selection == 0:
            if self.parent.plot_parameters['ImgScale'] != 'linear':
                self.parent.img[self.parent.imgZeros] = 0.0
                self.ImgObj.set_data(self.parent.img)
                self.ImgObj.changed()
                self.parent.plot_parameters['ImgScale'] = 'linear'
                
                if self.parent.plot_parameters['ClimLocked'] == False:
                    minval = self.parent.img.min()
                    maxval = self.parent.img.max()
                    
                    self.parent.plot_parameters['UpperClim'] = maxval
                    self.parent.plot_parameters['LowerClim'] = minval
                    
                    self.ImgObj.set_clim(minval, maxval)
                    self.resetSliders(maxval, minval)
                
                self.parent.updateImage()
        if selection == 1:
            if self.parent.plot_parameters['ImgScale'] != 'logarithmic':
                
                self.parent.img[self.parent.imgZeros] = 1.0
                
                self.newImg = log(self.parent.img)
                self.newImg = uint16(self.newImg / self.newImg.max() * 65535)
                 
                self.ImgObj.set_data(self.newImg)
                self.ImgObj.changed()
                self.parent.plot_parameters['ImgScale'] = 'logarithmic'
                
                if self.parent.plot_parameters['ClimLocked'] == False:
                    minval = self.newImg.min()
                    maxval = self.newImg.max()
                    
                    self.parent.plot_parameters['UpperClim'] = maxval
                    self.parent.plot_parameters['LowerClim'] = minval
                    
                    self.ImgObj.set_clim(minval, maxval)
                    self.resetSliders(maxval, minval)
                
                self.parent.updateImage()
                
                  
    def createSettingsWindow(self):
        
        finalSizer = wx.BoxSizer(wx.VERTICAL)
        
        for each in self.sliderinfo:
                
            label = wx.StaticText(self, -1, each[0])
            val = wx.TextCtrl(self, each[1], size = (60, 21), style = wx.TE_PROCESS_ENTER)
            val.Bind(wx.EVT_TEXT_ENTER, self.OnTxtEnter)
            val.Bind(wx.EVT_KILL_FOCUS, self.OnTxtEnter)
            
            slider = wx.Slider(self, each[2], style = wx.HORIZONTAL)
            
            if platform.system() == 'Darwin':
                #slider.Bind(wx.EVT_SLIDER, self.OnSlider)
                slider.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.OnSlider)
            else:
                slider.Bind(wx.EVT_SCROLL_CHANGED, self.OnSlider)
            
            #slider.Bind(wx.EVT_LEFT_UP, self.OnTest)
            
            if each[3] == 'Brightness' or each[3] == 'Contrast':
                slider.SetMin(0)
                slider.SetMax(200)
                slider.Enable(False)
            else:
                
                slider.SetMin(int(self.minval))
                slider.SetMax(min(int(self.maxval), 65534))
            
            if self.parent.plot_parameters[each[3]] != None:
                val.SetValue(str(    min(self.parent.plot_parameters[each[3]], 65534)   ))
                slider.SetValue(float(   min(self.parent.plot_parameters[each[3]], 65534   )))
            
            hslider = wx.BoxSizer(wx.HORIZONTAL)
               
            hslider.Add(label, 0, wx.EXPAND | wx.TOP, 3)
            hslider.Add(val, 0, wx.EXPAND)
            hslider.Add(slider, 1, wx.EXPAND)
           
            finalSizer.Add(hslider, 0, wx.EXPAND)
        
        chkbox = wx.CheckBox(self, -1, 'Lock values')
        chkbox.Bind(wx.EVT_CHECKBOX, self.onLockValues)
        chkbox.SetValue(self.parent.plot_parameters['ClimLocked'])
        
        finalSizer.Add(chkbox, 0, wx.EXPAND | wx.TOP, 3)

        return finalSizer
    
    def OnTest(self, event):
        print 'BAM!'
    
    def resetSliders(self, maxval, minval):
        
        for each in self.sliderinfo:
            txtCtrl = wx.FindWindowById(each[1])
            slider = wx.FindWindowById(each[2])
            txtCtrl.SetValue(str(self.parent.plot_parameters[each[3]]))
            
            if each[3] == 'Brightness' or each[3] == 'Contrast':
                slider.SetMin(0)
                slider.SetMax(200)
            else:
                slider.SetMin(minval)
                slider.SetMax(maxval)
            
            
            slider.SetValue(float(self.parent.plot_parameters[each[3]]))
    
    def onLockValues(self, event):
        
        if event.GetEventObject().IsChecked():
            self.parent.plot_parameters['ClimLocked'] = True
        else:
            self.parent.plot_parameters['ClimLocked'] = False
    
    def OnTxtEnter(self, event):

        id = event.GetId()
        
        for each in self.sliderinfo:
            if each[1] == id:
                ctrl = wx.FindWindowById(id)
                slider = wx.FindWindowById(each[2])
                slider.SetValue(float(ctrl.GetValue()))
                
                val = ctrl.GetValue()
                self.parent.plot_parameters[each[3]] = float(val)
                
                if each[3] == 'Brightness' or each[3] == 'Contrast':
                    self.setBrightnessAndContrastUINT16()
                else:
                    self.parent.updateClim()

    def OnSlider(self, event):
        
        id = event.GetId()
        
        for each in self.sliderinfo:
            if each[2] == id:        
                slider = event.GetEventObject()
                val = slider.GetValue()    
                wx.FindWindowById(each[1]).SetValue(str(val))
                self.parent.plot_parameters[each[3]] = float(val)
                
                if each[3] == 'Brightness' or each[3] == 'Contrast':
                    self.setBrightnessAndContrastUINT16()
                else:
                    self.parent.updateClim()
            
    def setBrightnessAndContrastUINT16(self):
        brightness = self.parent.plot_parameters['Brightness'] - 100;
        contrast = (self.parent.plot_parameters['Contrast'] - 100)/10;
        max_value = 0;
        
        print brightness
        print contrast
        
        lut = np.array(range(0,65536), int)

    # The algorithm is by Werner D. Streidt
    # (http://visca.com/ffactory/archives/5-99/msg00021.html)
        if( contrast > 0 ):
            delta = 32767.*contrast/100;
            a = 65535./(65535. - delta*2);
            b = a*(brightness - delta);
        else:
            delta = -32768.*contrast/100;
            a = (65536.-delta*2)/65535.;
            b = a*brightness + delta;

        for i in range(65536):
            v = round(a*i + b);
            if( v < 0 ):
                v = 0;
            if( v > 65535 ):
                v = 65535;
            lut[i] = v;
    
        newImg = lut[np.int(self.parent.img)]
        
        
      #  if self.parent.plot_parameters['ImgScale'] != 'logarithmic':
      #      newImg[where(newImg) == 0] = 1.0
      #      newImg = log(self.parent.img)
      #      newImg = uint16(self.newImg / self.newImg.max() * 65535)
                 
                #self.ImgObj.set_data(self.newImg)
#       newImg[where(newImg<1)] = 1
        self.ImgObj.set_data(newImg)
        self.parent.updateImage()

#--- ** FOR TESTING **
class ImageTestFrame(wx.Frame):
    ''' A Frame for testing the image panel '''
    
    def __init__(self, title, frame_id):
        wx.Frame.__init__(self, None, frame_id, title, name = 'MainFrame')
        
        self.SetSize((500,500))  
        self.RAWWorkDir = '.'
        self.raw_settings = RAWSettings.RawGuiSettings()
        
        self.background_panel = wx.Panel(self, -1)
        
        sizer = wx.BoxSizer()
        
        self.image_panel = ImagePanel(self.background_panel, -1, 'RawPlotPanel')
        
        sizer.Add(self.image_panel, 1, wx.GROW)
  
        self.background_panel.SetSizer(sizer)
        
        self.statusbar = self.CreateStatusBar()
        self.statusbar.SetFieldsCount(3)
         
        self.SetStatusBar(self.statusbar)
        
        self.loadTestImage()
        
    def loadTestImage(self):
        
        file = os.path.join(os.getcwd(), 'Tests', 'TestData', 'AgBe_Quantum.img')
        sasm, img = SASFileIO.loadFile(file, self.raw_settings)
        self.image_panel.showImage(img, sasm)
        
        
class ImageTestApp(wx.App):
    ''' A test app '''
    
    def OnInit(self):
        
        frame = ImageTestFrame('Options', -1)
        self.SetTopWindow(frame)
        frame.CenterOnScreen()
        frame.Show(True) 
        return True
    
if __name__ == "__main__":
    import RAWSettings
    import SASFileIO
    
    app = ImageTestApp(0)   #MyApp(redirect = True)
    app.MainLoop()

