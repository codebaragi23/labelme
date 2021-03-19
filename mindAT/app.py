# -*- coding: utf-8 -*-

import functools
import math
import os
import os.path as osp
import shutil
import webbrowser
import numpy as np

import collections
import datetime
import uuid
import json

import pycocotools.mask as cocomask

import lxml.builder
import lxml.etree

import imgviz
from PIL import Image, ImageEnhance
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy.QtCore import Slot
from qtpy import QtGui
from qtpy import QtWidgets

from mindAT import __appname__
from mindAT import __version__
from mindAT import PY2
from mindAT import QT5

from . import utils
from mindAT.config import get_config
from mindAT.label_file import LabelFile
from mindAT.label_file import LabelFileError
from mindAT.logger import logger
from mindAT.annotation import Annotation
from mindAT.widgets import AppearanceWidget
from mindAT.widgets import Canvas
from mindAT.widgets import LabelDialog
from mindAT.widgets import AnnotationListWidget
from mindAT.widgets import AnnotationListWidgetItem
from mindAT.widgets import ToolBar
from mindAT.widgets import LabelQListWidget
from mindAT.widgets import ZoomWidget

LABEL_COLORMAP = imgviz.label_colormap(value=None)
class MainWindow(QtWidgets.QMainWindow):

  FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2
  RESTART_CODE = 0x1234
  RESET_CONFIG = 0x4321

  def __init__(
    self,
    support_languages,
    config=None,
    filename=None,
    output=None,
    output_file=None,
    output_dir=None,
  ):
    if output is not None:
      logger.warning(
        "argument output is deprecated, use output_file instead"
      )
      if output_file is None:
        output_file = output

    # see mindAT/config/default_config.yaml for valid configuration
    # save default config to ~/.mindATrc
    if config is None:
      config = get_config()
    self.config = config
    self.resetConfig = False
    self.support_languages = support_languages

    # set default annotation colors
    Annotation.line_color = QtGui.QColor(*self.config["annotation"]["line_color"])
    Annotation.fill_color = QtGui.QColor(*self.config["annotation"]["fill_color"])
    Annotation.select_line_color = QtGui.QColor(
      *self.config["annotation"]["select_line_color"]
    )
    Annotation.select_fill_color = QtGui.QColor(
      *self.config["annotation"]["select_fill_color"]
    )
    Annotation.vertex_fill_color = QtGui.QColor(
      *self.config["annotation"]["vertex_fill_color"]
    )
    Annotation.hvertex_fill_color = QtGui.QColor(
      *self.config["annotation"]["hvertex_fill_color"]
    )

    super(MainWindow, self).__init__()
    self.setWindowTitle(__appname__)

    # Whether we need to save or not.
    self.dirty = False

    self._noSelectionSlot = False

    self.workerFile = None

    # Main widgets and related state.
    self.labelDialog = LabelDialog(
      parent=self,
      labels=self.config["labels"],
      sort_labels=self.config["sort_labels"],
      show_text_field=self.config["show_label_text_field"],
      completion=self.config["label_completion"],
      fit_to_content=self.config["fit_to_content"],
      flags=self.config["label_flags"],
    )

    self.lastOpenDir = None
    
    self.fileListPath = QtWidgets.QLineEdit()
    self.fileListPath.setPlaceholderText(self.tr("Path"))
    self.fileListPath.addAction(utils.newIcon("open"), QtWidgets.QLineEdit.LeadingPosition)
    self.fileListPath.setReadOnly(True)

    self.fileSearch = QtWidgets.QLineEdit()
    self.fileSearch.setPlaceholderText(self.tr("Search Filename"))
    self.fileSearch.textChanged.connect(self.fileSearchChanged)
    self.fileListWidget = QtWidgets.QListWidget()
    self.fileListWidget.itemSelectionChanged.connect(self.fileSelectionChanged)
    fileListLayout = QtWidgets.QVBoxLayout()
    fileListLayout.setContentsMargins(0, 0, 0, 0)
    fileListLayout.setSpacing(0)
    fileListLayout.addWidget(self.fileListPath)
    fileListLayout.addSpacing(5)
    fileListLayout.addWidget(self.fileSearch)
    fileListLayout.addWidget(self.fileListWidget)
    fileListWidget = QtWidgets.QWidget()
    fileListWidget.setLayout(fileListLayout)
    self.file_dock = QtWidgets.QDockWidget(self.tr(u"File List"), self)
    self.file_dock.setObjectName(u"Files")
    self.file_dock.setWidget(fileListWidget)

    self.appearance_widget = AppearanceWidget(self.onAppearanceChangedCallback)
    self.appearance_widget.setEnabled(False)
    self.appe_dock = QtWidgets.QDockWidget(self.tr(u"Appearance"), self)
    self.appe_dock.setObjectName(u"Appearance")
    self.appe_dock.setWidget(self.appearance_widget)
    
    self.flag_dock = self.flag_widget = None
    self.flag_dock = QtWidgets.QDockWidget(self.tr("Flags"), self)
    self.flag_dock.setObjectName("Flags")
    self.flag_widget = QtWidgets.QListWidget()
    if config["flags"]:
      self.loadFlags({k: False for k in config["flags"]})
    self.flag_dock.setWidget(self.flag_widget)
    self.flag_widget.itemChanged.connect(self.setDirty)

    self.labelList = LabelQListWidget()
    self.labelList.setToolTip(
      self.tr(
        "Select label to start annotating for it. "
        "Press 'Esc' to deselect."
      )
    )
    if self.config["labels"]:
      for label in self.config["labels"]:
        item = self.labelList.createItemFromLabel(label)
        self.labelList.addItem(item)
        rgb = self._get_rgb_by_label(label)
        self.labelList.setItemLabel(item, label, rgb)

    self.annotList = AnnotationListWidget()
    self.annotList.itemSelectionChanged.connect(self.annotSelectionChanged)
    self.annotList.itemDoubleClicked.connect(self.editLabel)
    self.annotList.itemChanged.connect(self.annotItemChanged)
    self.annotList.itemDropped.connect(self.annotOrderChanged)

    labelListSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
    labelListSplitter.addWidget(utils.addTitle(self.labelList, self.tr("Labels")))
    labelListSplitter.addWidget(utils.addTitle(self.annotList, self.tr("Annotations")))
    labelListSplitter.setCollapsible(0, False)
    labelListSplitter.setCollapsible(1, False)
    labelListSplitter.setStretchFactor(0, 3)
    labelListSplitter.setStretchFactor(1, 7)
    labelListSplitter.setHandleWidth(7)

    labelListLayout = QtWidgets.QVBoxLayout()
    labelListLayout.setContentsMargins(0, 0, 0, 0)
    labelListLayout.addWidget(labelListSplitter)

    labelListWidget = QtWidgets.QWidget()
    labelListWidget.setLayout(labelListLayout)
    self.label_dock = QtWidgets.QDockWidget(self.tr("Label List"), self)
    self.label_dock.setObjectName(u"Labels")
    self.label_dock.setWidget(labelListWidget)

    self.zoomWidget = ZoomWidget()
    self.setAcceptDrops(True)

    self.canvas = self.annotList.canvas = Canvas(
      epsilon=self.config["epsilon"],
      double_click=self.config["canvas"]["double_click"],
    )
    self.canvas.zoomRequest.connect(self.zoomRequest)

    scrollArea = QtWidgets.QScrollArea()
    scrollArea.setWidget(self.canvas)
    scrollArea.setWidgetResizable(True)
    self.scrollBars = {
      Qt.Vertical: scrollArea.verticalScrollBar(),
      Qt.Horizontal: scrollArea.horizontalScrollBar(),
    }
    self.canvas.scrollRequest.connect(self.scrollRequest)

    self.canvas.newAnnotation.connect(self.newAnnotation)
    self.canvas.annotationMoved.connect(self.setDirty)
    self.canvas.selectionChanged.connect(self.annotationSelectionChanged)
    self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

    self.setCentralWidget(scrollArea)

    features = QtWidgets.QDockWidget.DockWidgetFeatures()
    for dock in ["file_dock", "flag_dock", "label_dock"]:
      if self.config[dock]["closable"]:
        features = features | QtWidgets.QDockWidget.DockWidgetClosable
      if self.config[dock]["floatable"]:
        features = features | QtWidgets.QDockWidget.DockWidgetFloatable
      if self.config[dock]["movable"]:
        features = features | QtWidgets.QDockWidget.DockWidgetMovable
      getattr(self, dock).setFeatures(features)
      if self.config[dock]["show"] is False:
        getattr(self, dock).setVisible(False)

    self.setTabPosition(Qt.RightDockWidgetArea, QtWidgets.QTabWidget.North)
    
    self.addDockWidget(Qt.LeftDockWidgetArea, self.file_dock)
    self.addDockWidget(Qt.LeftDockWidgetArea, self.appe_dock)
    self.addDockWidget(Qt.RightDockWidgetArea, self.label_dock)
    self.tabifyDockWidget(self.label_dock, self.flag_dock)
    
    # Actions
    action = functools.partial(utils.newAction, self)
    shortcuts = self.config["shortcuts"]
    quit = action(
      self.tr("&Quit"),
      self.close,
      shortcuts["quit"],
      "quit",
      self.tr("Quit application"),
    )
    open_ = action(
      self.tr("&Open"),
      self.openFile,
      shortcuts["open"],
      "open",
      self.tr("Open image or label file"),
    )
    opendir = action(
      self.tr("&Open Dir"),
      self.openDirDialog,
      shortcuts["open_dir"],
      "open",
      self.tr(u"Open Dir"),
    )
    openNextImg = action(
      self.tr("Next Image"),
      self.openNextImg,
      shortcuts["open_next"],
      "next",
      self.tr(u"Open next image"),
      enabled=False,
    )
    openPrevImg = action(
      self.tr("Prev Image"),
      self.openPrevImg,
      shortcuts["open_prev"],
      "prev",
      self.tr(u"Open previous image"),
      enabled=False,
    )
    save = action(
      self.tr("&Save"),
      self.saveFile,
      shortcuts["save"],
      "save",
      self.tr("Save labels to file"),
      enabled=False,
    )
    saveAs = action(
      self.tr("&Save As"),
      self.saveFileAs,
      shortcuts["save_as"],
      "save-as",
      self.tr("Save labels to a different file"),
      enabled=False,
    )

    deleteFile = action(
      self.tr("&Delete File"),
      self.deleteFile,
      shortcuts["delete_file"],
      "delete",
      self.tr("Delete current label file"),
      enabled=False,
    )

    saveAuto = action(
      text=self.tr("Save &Automatically"),
      slot=lambda x: self.actions.saveAuto.setChecked(x),
      icon="save",
      tip=self.tr("Save automatically"),
      checkable=True,
      enabled=True,
    )
    saveAuto.setChecked(self.config["auto_save"])

    saveWithImageData = action(
      text=self.tr("Save With Image Data"),
      slot=self.enableSaveImageWithData,
      tip=self.tr("Save image data in label file"),
      checkable=True,
      checked=self.config["store_data"],
    )

    changeOutputDir = action(
      text=self.tr("Change &Output Dir"),
      slot=self.onChangeOutputDir,
      shortcut=shortcuts["save_to"],
      icon="open",
      tip=self.tr(u"Change where annotations are loaded/saved"),
    )
    
    changeLanguage = action(
      text=self.tr("Change &Language"),
      slot=self.onChangeLanguage,
      icon="translate",
      tip=self.tr(u"Change display language"),
    )

    resetConfiguration = action(
      text=self.tr("&Reset Configuration"),
      slot=self.onResetConfig,
      icon="reset",
      tip=self.tr(u"Reset configuration from configuraton file"),
    )

    close = action(
      text=self.tr("&Close"),
      slot=self.closeFileDir,
      shortcut=shortcuts["close"],
      icon="close",
      tip=self.tr("Close current file or directory"),
    )

    toggle_keep_prev_mode = action(
      text=self.tr("Keep Previous Annotation"),
      slot=self.toggleKeepPrevMode,
      shortcut=shortcuts["toggle_keep_prev_mode"],
      tip=self.tr('Toggle "keep pevious annotation" mode'),
      checkable=True,
    )
    toggle_keep_prev_mode.setChecked(self.config["keep_prev"])

    createPolyMode = action(
      text=self.tr("Create Polygons"),
      slot=lambda: self.toggleDrawMode(self.actions.createPolyMode),
      shortcut=shortcuts["create_polygon"],
      icon="polygon",
      tip=self.tr("Start drawing polygons"),
      enabled=False,
      checkable=True,
    )
    createRectangleMode = action(
      text=self.tr("Create Rectangle"),
      slot=lambda: self.toggleDrawMode(self.actions.createRectangleMode),
      shortcut=shortcuts["create_rectangle"],
      icon="rectangle",
      tip=self.tr("Start drawing rectangles"),
      enabled=False,
      checkable=True,
    )
    createCircleMode = action(
      text=self.tr("Create Circle"),
      slot=lambda: self.toggleDrawMode(self.actions.createCircleMode),
      shortcut=shortcuts["create_circle"],
      icon="circle",
      tip=self.tr("Start drawing circles"),
      enabled=False,
      checkable=True,
    )
    createLineMode = action(
      text=self.tr("Create Line"),
      slot=lambda: self.toggleDrawMode(self.actions.createLineMode),
      shortcut=shortcuts["create_line"],
      icon="line",
      tip=self.tr("Start drawing lines"),
      enabled=False,
      checkable=True,
    )
    createPointMode = action(
      text=self.tr("Create Point"),
      slot=lambda: self.toggleDrawMode(self.actions.createPointMode),
      shortcut=shortcuts["create_point"],
      icon="point",
      tip=self.tr("Start drawing points"),
      enabled=False,
      checkable=True,
    )
    createLineStripMode = action(
      text=self.tr("Create LineStrip"),
      slot=lambda: self.toggleDrawMode(self.actions.createLineStripMode),
      shortcut=shortcuts["create_linestrip"],
      icon="line_strip",
      tip=self.tr("Start drawing linestrip (Ctrl+LeftClick ends creation)"),
      enabled=False,
      checkable=True,
    )

    movableMode = action(
      text=self.tr("Move"),
      slot=self.toggleMoveMode,
      shortcut=shortcuts["move_annotation"],
      icon="move",
      tip=self.tr("Move the selected annotations"),
      enabled=False,
      checkable=True,
    )
    
    copy = action(
      text=self.tr("Duplicate Annotations"),
      slot=self.copySelectedAnnotation,
      shortcut=shortcuts["duplicate_annotation"],
      icon="copy",
      tip=self.tr("Create a duplicate of the selected annotations"),
      enabled=False,
    )
    delete = action(
      text=self.tr("Delete Annotations"),
      slot=self.onDeleteSelectedAnnotation,
      shortcut=shortcuts["delete_annotation"],
      icon="cancel",
      tip=self.tr("Delete the selected annotations"),
      enabled=False,
    )

    undo = action(
      self.tr("Undo"),
      self.undoAnnotationEdit,
      shortcuts["undo"],
      "undo",
      self.tr("Undo last add and edit of annotation"),
      enabled=False,
    )
    undoLastPoint = action(
      text=self.tr("Undo last point"),
      slot=self.canvas.undoLastPoint,
      shortcut=shortcuts["undo_last_point"],
      icon="undo",
      tip=self.tr("Undo last drawn point"),
      enabled=False,
    )

    addPointToEdge = action(
      text=self.tr("Add Point to Edge"),
      slot=self.canvas.addPointToEdge,
      shortcut=shortcuts["add_point_to_edge"],
      icon="edit",
      tip=self.tr("Add point to the nearest edge"),
      enabled=False,
    )
    removePoint = action(
      text=self.tr("Remove Selected Point"),
      slot=self.canvas.removeSelectedPoint,
      icon="edit",
      tip=self.tr("Remove selected point from polygon"),
      enabled=False,
    )

    hideAll = action(
      self.tr("&Hide Polygons"),
      functools.partial(self.togglePolygons, False),
      icon="eye",
      tip=self.tr("Hide all polygons"),
      enabled=False,
    )
    showAll = action(
      self.tr("&Show Polygons"),
      functools.partial(self.togglePolygons, True),
      icon="eye",
      tip=self.tr("Show all polygons"),
      enabled=False,
    )

    help = action(
      self.tr("&Tutorial"),
      self.tutorial,
      icon="help",
      tip=self.tr("Show tutorial page"),
    )

    zoom = QtWidgets.QWidgetAction(self)
    zoom.setDefaultWidget(self.zoomWidget)
    self.zoomWidget.setWhatsThis(
      self.tr(
        "Zoom in or out of the image. Also accessible with "
        "{} and {} from the canvas."
      ).format(
        utils.fmtShortcut(
          "{},{}".format(shortcuts["zoom_in"], shortcuts["zoom_out"])
        ),
        utils.fmtShortcut(self.tr("Ctrl+Wheel")),
      )
    )
    self.zoomWidget.setEnabled(False)

    zoomIn = action(
      self.tr("Zoom &In"),
      functools.partial(self.addZoom, 1.1),
      shortcuts["zoom_in"],
      "zoom-in",
      self.tr("Increase zoom level"),
      enabled=False,
    )
    zoomOut = action(
      self.tr("&Zoom Out"),
      functools.partial(self.addZoom, 0.9),
      shortcuts["zoom_out"],
      "zoom-out",
      self.tr("Decrease zoom level"),
      enabled=False,
    )
    zoomOrg = action(
      self.tr("&Original size"),
      functools.partial(self.setZoom, 100),
      shortcuts["zoom_to_original"],
      "zoom",
      self.tr("Zoom to original size"),
      enabled=False,
    )
    fitWindow = action(
      self.tr("&Fit Window"),
      self.setFitWindow,
      shortcuts["fit_window"],
      "fit-window",
      self.tr("Zoom follows window size"),
      checkable=True,
      enabled=False,
    )
    fitWidth = action(
      self.tr("Fit &Width"),
      self.setFitWidth,
      shortcuts["fit_width"],
      "fit-width",
      self.tr("Zoom follows window width"),
      checkable=True,
      enabled=False,
    )
    # Group zoom controls into a list for easier toggling.
    zoomActions = (
      self.zoomWidget,
      zoomIn,
      zoomOut,
      zoomOrg,
      fitWindow,
      fitWidth,
    )
    self.zoomMode = self.FIT_WINDOW
    fitWindow.setChecked(Qt.Checked)
    self.scalers = {
      self.FIT_WINDOW: self.scaleFitWindow,
      self.FIT_WIDTH: self.scaleFitWidth,
      # Set to one to scale to 100% when loading files.
      self.MANUAL_ZOOM: lambda: 1,
    }

    labelEdit = action(
      self.tr("&Edit Label"),
      self.editLabel,
      shortcuts["edit_label"],
      "edit",
      self.tr("Modify the label of the selected polygon"),
      enabled=False,
    )

    exportPixel = action(
      "Pixel Map",
      slot=self.onExportPixelMap,
      icon="export",
      tip=self.tr("Export pixel labeling"),
      enabled=False,
    )

    exportVOC = action(
      "VOC",
      slot=self.onExportVOC,
      icon="export",
      tip=self.tr("Export VOC dataset format"),
      enabled=False,
    )

    exportCOCO = action(
      "COCO",
      slot=self.onExportCOCO,
      icon="export",
      tip=self.tr("Export COCO dataset format"),
      enabled=False,
    )

    # Lavel list context menu.
    labelMenu = QtWidgets.QMenu()
    utils.addActions(labelMenu, (labelEdit, delete))
    self.annotList.setContextMenuPolicy(Qt.CustomContextMenu)
    self.annotList.customContextMenuRequested.connect(
      self.popLabelListMenu
    )

    # Store actions for further handling.
    self.actions = utils.struct(
      saveAuto=saveAuto,
      saveWithImageData=saveWithImageData,
      changeOutputDir=changeOutputDir,
      save=save,
      saveAs=saveAs,
      open=open_,
      close=close,
      deleteFile=deleteFile,
      toggleKeepPrevMode=toggle_keep_prev_mode,
      delete=delete,
      edit=labelEdit,
      copy=copy,
      undoLastPoint=undoLastPoint,
      undo=undo,
      addPointToEdge=addPointToEdge,
      removePoint=removePoint,

      createPolyMode=createPolyMode,
      createRectangleMode=createRectangleMode,
      createCircleMode=createCircleMode,
      createLineMode=createLineMode,
      createPointMode=createPointMode,
      createLineStripMode=createLineStripMode,

      movableMode=movableMode,

      zoom=zoom,
      zoomIn=zoomIn,
      zoomOut=zoomOut,
      zoomOrg=zoomOrg,
      fitWindow=fitWindow,
      fitWidth=fitWidth,
      zoomActions=zoomActions,
      openNextImg=openNextImg,
      openPrevImg=openPrevImg,
      fileMenuActions=(open_, opendir, save, saveAs, close, quit),
      tool=(),
      
      annotCheckableOperations=(
        createPolyMode,
        createRectangleMode,
        createCircleMode,
        createLineMode,
        createPointMode,
        createLineStripMode,
      ),

      extraCheckableOperations = (
        movableMode,
      ),

      # XXX: need to add some actions here to activate the shortcut
      editMenu=(
        None,
        labelEdit,
        None,
        copy,
        delete,
        None,
        undo,
        undoLastPoint,
        None,
        addPointToEdge,
        None,
        toggle_keep_prev_mode,
      ),

      # menu shown at right click
      menu=(
        labelEdit,
        copy,
        delete,
        None,
        undo,
        undoLastPoint,
        None,
        addPointToEdge,
        removePoint,
      ),

      onLoadActive=(
        close,
        createPolyMode,
        createRectangleMode,
        createCircleMode,
        createLineMode,
        createPointMode,
        createLineStripMode,
      ),
      onAnnotationsPresent=(saveAs, hideAll, showAll),
      exportDetectMenu=(
        exportVOC,
      ),
      exportSegMenu=(
        exportPixel,
        exportVOC,
        exportCOCO,
      ),
    )

    self.canvas.edgeSelected.connect(self.canvasAnnotationEdgeSelected)
    self.canvas.vertexSelected.connect(self.actions.removePoint.setEnabled)

    self.menus = utils.struct(
      file=self.menu(self.tr("&File")),
      edit=self.menu(self.tr("&Edit")),
      view=self.menu(self.tr("&View")),
      data=self.menu(self.tr("&Dataset")),
      help=self.menu(self.tr("&Help")),
      recentFiles=QtWidgets.QMenu(self.tr("Open &Recent")),
      preferences=QtWidgets.QMenu(self.tr("&Preferences")),
      export_=QtWidgets.QMenu(self.tr("&Export")),
      labelList=labelMenu,
    )
    
    utils.addActions(
      self.menus.file,
      (
        open_,
        openNextImg,
        openPrevImg,
        opendir,
        self.menus.recentFiles,
        None,
        save,
        saveAs,
        saveAuto,
        saveWithImageData,
        None,
        self.menus.preferences,
        None,
        close,
        deleteFile,
        None,
        quit,
      ),
    )

    utils.addActions(
      self.menus.preferences,
      (
        changeOutputDir,
        changeLanguage,
        resetConfiguration,
      ),
    )

    utils.addActions(
      self.menus.view,
      (
        self.file_dock.toggleViewAction(),
        self.appe_dock.toggleViewAction(),
        self.flag_dock.toggleViewAction(),
        self.label_dock.toggleViewAction(),
        None,
        hideAll,
        showAll,
        None,
        zoomIn,
        zoomOut,
        zoomOrg,
        None,
        fitWindow,
        fitWidth,
        None,
      ),
    )

    utils.addActions(
      self.menus.data,
      (
        self.menus.export_,
      ),
    )

    utils.addActions(
      self.menus.export_,
      (
        exportPixel,
        exportVOC,
        exportCOCO,
      ),
    )
    self.menus.export_.setEnabled(False)

    utils.addActions(self.menus.help, (help,))

    self.menus.file.aboutToShow.connect(self.updateFileMenu)

    # Custom context menu for the canvas widget:
    utils.addActions(self.canvas.menus[0], self.actions.menu)
    utils.addActions(
      self.canvas.menus[1],
      (
        action("&Copy here", self.copyAnnotation),
        action("&Move here", self.moveAnnotation),
      ),
    )

    self.action_to_shape = {
      self.actions.createPolyMode : "polygon",
      self.actions.createRectangleMode : "rectangle",
      self.actions.createCircleMode : "circle",
      self.actions.createLineMode : "line",
      self.actions.createPointMode : "point",
      self.actions.createLineStripMode : "linestrip",
    }

    # Menu buttons on Left
    self.actions.annotTool = (
      createPolyMode,
      createRectangleMode,
      createCircleMode,
      createLineMode, 
      createPointMode,
      createLineStripMode,
      None,
      movableMode,
      None,
      copy,
      delete,
      undo,
      None,
      zoom,
      fitWidth,
    )

    self.actions.filemenuTool = (
      open_,
      opendir,
      save,
    )

    self.actions.filemenuTool = (
      open_,
      opendir,
      save,
    )
    self.actions.playTool = (
      openPrevImg,
      openNextImg,
    )

    self.statusBar().showMessage(self.tr("%s started.") % __appname__)
    self.statusBar().show()

    if output_file is not None and self.config["auto_save"]:
      logger.warn(
        "If `auto_save` argument is True, `output_file` argument "
        "is ignored and output filename is automatically "
        "set as IMAGE_BASENAME.json."
      )
    self.output_file = output_file
    self.output_dir = output_dir

    # Application state.
    self.image = QtGui.QImage()
    self.imagePath = None
    self.recentFiles = []
    self.maxRecent = 7
    self.zoom_level = 100
    self.fit_window = False
    self.zoom_values = {}  # key=filename, value=(zoom_mode, zoom_value)
    self.scroll_values = {
      Qt.Horizontal: {},
      Qt.Vertical: {},
    }  # key=filename, value=scroll_value

    if filename is not None and osp.isdir(filename):
      self.importDirImages(filename, load=False)
    else:
      self.filename = filename

    if config["file_search"]:
      self.fileSearch.setText(config["file_search"])
      self.fileSearchChanged()

    # XXX: Could be completely declarative.
    # Restore application settings.

    # /$HOME/.config/mindAT
    self.settings = QtCore.QSettings("mindAT", "mindAT")

    # FIXME: QSettings.value can return None on PyQt4
    self.recentFiles = self.settings.value("recentFiles", []) or []
    size = self.settings.value("window/size", QtCore.QSize(800, 500))
    position = self.settings.value("window/position", QtCore.QPoint(0, 0))
    self.resize(size)
    self.move(position)
    # or simply:
    self.restoreState(
      self.settings.value("window/state", QtCore.QByteArray())
    )
    self.file_dock.raise_()
    #self.file_dock.hide()

    # Populate the File menu dynamically.
    self.updateFileMenu()
    # Since loading the file may take some time,
    # make sure it runs in the background.
    if self.filename is not None:
      self.queueEvent(functools.partial(self.loadFile, self.filename))

    # Callbacks:
    self.zoomWidget.valueChanged.connect(self.paintCanvas)

    # Toolbars
    if hasattr(self.actions, 'annotTool'):
      toolbar = ToolBar("annotTools")
      toolbar.setObjectName("annotTools-ToolBar")
      toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon | Qt.ToolButtonTextBesideIcon)
      # size = toolbar.iconSize()
      # size.setWidth(size.width()*1.5)
      # toolbar.setIconSize(size)
      utils.addActions(toolbar, self.actions.annotTool)
      self.addToolBar(Qt.LeftToolBarArea, toolbar)

    if hasattr(self.actions, 'filemenuTool'):
      toolbar = ToolBar("filemenuTool")
      toolbar.setObjectName("filemenuTool-ToolBar")
      toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon | Qt.ToolButtonTextBesideIcon)
      toolbar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
      utils.addActions(toolbar, self.actions.filemenuTool)
      self.addToolBar(Qt.TopToolBarArea, toolbar)

    if hasattr(self.actions, 'playTool'):
      toolbar = ToolBar("playTool")
      toolbar.setObjectName("playTool-ToolBar")
      toolbar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

      spacer = QtWidgets.QWidget()
      spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
      toolbar.addWidget(spacer)
      utils.addActions(toolbar, self.actions.playTool)
      spacer = QtWidgets.QWidget()
      spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
      toolbar.addWidget(spacer)
      
      toolbar.setStyleSheet("QToolButton { padding-left: 40px; padding-right: 40px; }")
      self.addToolBar(Qt.TopToolBarArea, toolbar)

    self.populateModeActions()

  def menu(self, title, actions=None):
    menu = self.menuBar().addMenu(title)
    if actions:
      utils.addActions(menu, actions)
    return menu

  # Support Functions
  def noAnnotations(self):
    return not len(self.annotList)

  def populateModeActions(self):
    menu = self.actions.menu
    self.canvas.menus[0].clear()      
    utils.addActions(self.canvas.menus[0], menu)
    self.menus.edit.clear()
    utils.addActions(self.menus.edit, self.actions.annotCheckableOperations + self.actions.editMenu)

  def setDirty(self):
    if self.config["auto_save"] or self.actions.saveAuto.isChecked():
      label_file = self.getLabelFile(self.imagePath)
      if self.output_dir:
        label_file_without_path = osp.basename(label_file)
        label_file = osp.join(self.output_dir, label_file_without_path)
      self.saveLabels(label_file)
      return
    self.dirty = True
    self.actions.save.setEnabled(True)
    self.actions.undo.setEnabled(self.canvas.isAnnotationRestorable)
    
    title = __appname__
    if self.filename is not None:
      title = "{} - {}*".format(title, self.filename)
    self.setWindowTitle(title)

  def setClean(self):
    self.dirty = False
    self.actions.save.setEnabled(False)

    for action in self.actions.annotCheckableOperations + self.actions.extraCheckableOperations:
      action.setEnabled(True)
    
    title = __appname__
    if self.filename is not None:
      title = "{} - {}".format(title, self.filename)
    self.setWindowTitle(title)

    if self.hasLabelFile():
      self.actions.deleteFile.setEnabled(True)
      self.menus.export_.setEnabled(True)
    else:
      self.actions.deleteFile.setEnabled(False)
      self.menus.export_.setEnabled(False)

  def toggleActions(self, value=True):
    """Enable/Disable widgets which depend on an opened image."""
    for z in self.actions.zoomActions:
      z.setEnabled(value)

    for action in self.actions.onLoadActive:
      action.setEnabled(value)

  def canvasAnnotationEdgeSelected(self, selected, annotation):
    self.actions.addPointToEdge.setEnabled(
      selected and annotation and annotation.canAddPoint()
    )

  def queueEvent(self, function):
    QtCore.QTimer.singleShot(0, function)

  def status(self, message, delay=5000):
    self.statusBar().showMessage(message, delay)

  def resetState(self):
    if not self.config["labels"]:
      self.labelList.clear()
    self.annotList.clear()
    self.filename = None
    self.imagePath = None
    self.imageData = None
    self.labelFile = None
    self.workerFile = None
    self.otherData = None
    self.canvas.resetState()

  def currentItem(self):
    items = self.annotList.selectedItems()
    if items:
      return items[0]
    return None

  def addRecentFile(self, filename):
    if filename in self.recentFiles:
      self.recentFiles.remove(filename)
    elif len(self.recentFiles) >= self.maxRecent:
      self.recentFiles.pop()
    self.recentFiles.insert(0, filename)

  def undoAnnotationEdit(self):
    self.canvas.restoreAnnotation()
    self.annotList.clear()
    self.loadAnnotations(self.canvas.annotations)
    self.actions.undo.setEnabled(self.canvas.isAnnotationRestorable)

  def tutorial(self):
    url = "https://github.com/codebaragi23/mindAT/tree/master/examples/tutorial"  # NOQA
    webbrowser.open(url)

  def toggleDrawingSensitive(self, drawing=True):
    """Toggle drawing sensitive.

    In the middle of drawing, toggling between modes should be disabled.
    """
    self.actions.undoLastPoint.setEnabled(drawing)
    self.actions.undo.setEnabled(not drawing)
    self.actions.delete.setEnabled(not drawing)

  def updateFileMenu(self):
    current = self.filename

    def exists(filename):
      return osp.exists(str(filename))

    menu = self.menus.recentFiles
    menu.clear()
    files = [f for f in self.recentFiles if f != current and exists(f)]
    for i, f in enumerate(files):
      icon = utils.newIcon("labels")
      action = QtWidgets.QAction(
        icon, "&%d %s" % (i + 1, QtCore.QFileInfo(f).fileName()), self
      )
      action.triggered.connect(functools.partial(self.loadRecent, f))
      menu.addAction(action)

  def popLabelListMenu(self, point):
    if not self.canvas.editing():
      return;
      
    self.menus.labelList.exec_(self.annotList.mapToGlobal(point))

  def validateLabel(self, label):
    # no validation
    if self.config["validate_label"] is None:
      return True

    for i in range(self.labelList.count()):
      label_i = self.labelList.item(i).data(Qt.UserRole)
      if self.config["validate_label"] in ["exact"]:
        if label_i == label:
          return True
    return False

  def editLabel(self, item=None):
    if item and not isinstance(item, AnnotationListWidgetItem):
      raise TypeError("item must be AnnotationListWidgetItem type")

    if not self.canvas.editing():
      return
    if not item:
      item = self.currentItem()
    if item is None:
      return
    annotation = item.annotation()
    if annotation is None:
      return
    text, flags, group_id = self.labelDialog.popUp(
      text=annotation.label, flags=annotation.flags, group_id=annotation.group_id,
    )
    if text is None:
      return
    if not self.validateLabel(text):
      self.errorMessage(
        self.tr("Invalid label"),
        self.tr("Invalid label '{}' with validation type '{}'").format(
          text, self.config["validate_label"]
        ),
      )
      return
    annotation.label = text
    annotation.flags = flags
    annotation.flags = None
    annotation.group_id = group_id
    if annotation.group_id is None:
      item.setText(annotation.label)
    else:
      item.setText("{} ({})".format(annotation.label, annotation.group_id))
    if not self.labelList.findItemsByLabel(annotation.label):
      item = QtWidgets.QListWidgetItem()
      item.setData(Qt.UserRole, annotation.label)
      self.labelList.addItem(item)

    rgb = self._get_rgb_by_label(annotation.label)
    r, g, b = rgb
    item = self.annotList.findItemByAnnotation(annotation)
    item.setText(
      '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
        text, r, g, b
      )
    )
    annotation.setColor(rgb)
    self.setDirty()

  def fileSearchChanged(self):
    self.importDirImages(
      self.lastOpenDir, pattern=self.fileSearch.text(), load=False,
    )

  def fileSelectionChanged(self):
    items = self.fileListWidget.selectedItems()
    if not items:
      return
    item = items[0]

    if not self.mayContinue():
      return

    filelist = [osp.basename(full) for full in self.imageList]
    if item.text() in filelist:
      currIndex = filelist.index(item.text())
      if currIndex < len(self.imageList):
        filename = self.imageList[currIndex]
        self.loadFile(filename)

  # React to canvas signals.
  def annotationSelectionChanged(self, selected_annotations):
    self._noSelectionSlot = True
    for annotation in self.canvas.selectedAnnotations:
      annotation.selected = False
    self.annotList.clearSelection()
    self.canvas.selectedAnnotations = selected_annotations
    for annotation in self.canvas.selectedAnnotations:
      annotation.selected = True
      item = self.annotList.findItemByAnnotation(annotation)
      self.annotList.selectItem(item)
      self.annotList.scrollToItem(item)
    self._noSelectionSlot = False
    n_selected = len(selected_annotations)
    self.actions.delete.setEnabled(n_selected)
    self.actions.copy.setEnabled(n_selected)
    self.actions.edit.setEnabled(n_selected == 1)

  def addLabel(self, annotation):
    if annotation.group_id is None:
      text = annotation.label
    else:
      text = "{} ({})".format(annotation.label, annotation.group_id)
    annot_item = AnnotationListWidgetItem(text, annotation)
    self.annotList.addItem(annot_item)
    if not self.labelList.findItemsByLabel(annotation.label):
      label_item = self.labelList.createItemFromLabel(annotation.label)
      self.labelList.addItem(label_item)
      rgb = self._get_rgb_by_label(annotation.label)
      self.labelList.setItemLabel(label_item, annotation.label, rgb)
    self.labelDialog.addLabelHistory(annotation.label)
    for action in self.actions.onAnnotationsPresent:
      action.setEnabled(True)

    rgb = self._get_rgb_by_label(annotation.label)
    r, g, b = rgb
    annot_item.setText(
      '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
        text, r, g, b
      )
    )
    annotation.setColor(rgb)

  def _get_rgb_by_label(self, label):
    if self.config["annotation_color"] == "auto":
      item = self.labelList.findItemsByLabel(label)[0]
      label_id = self.labelList.indexFromItem(item).row() + 1
      label_id += self.config["shift_auto_annotation_color"]
      return LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)]
    elif (
      self.config["annotation_color"] == "manual"
      and self.config["labels"]
      and label in self.config["labels"]
    ):
      return self.config["labels"][label]["color"]
    elif self.config["default_annotation_color"]:
      return self.config["default_annotation_color"]

  def remLabels(self, annotations):
    for annotation in annotations:
      item = self.annotList.findItemByAnnotation(annotation)
      self.annotList.removeItem(item)

  def loadAnnotations(self, annotations, replace=True):
    self._noSelectionSlot = True
    for annotation in annotations:
      self.addLabel(annotation)
    self.annotList.clearSelection()
    self._noSelectionSlot = False
    self.canvas.loadAnnotations(annotations, replace=replace)
  
  def loadLabels(self, dict_annotations, avoidNested=False):
    annotations = [utils.dict_to_annotation(annotation, self.config["label_flags"]) for annotation in dict_annotations]
    if avoidNested:
      length = len(annotations)
      for sidx in range(length):
        src = annotations[sidx]
        for didx in range(0, annotations.index(src)):
          dst = annotations[didx]
          if src.contain(dst):
            annotations.remove(src)
            annotations.insert(annotations.index(dst), src)
            break

    self.loadAnnotations(annotations)

  def loadFlags(self, flags):
    self.flag_widget.clear()
    for key, flag in flags.items():
      item = QtWidgets.QListWidgetItem(key)
      item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
      item.setCheckState(Qt.Checked if flag else Qt.Unchecked)
      self.flag_widget.addItem(item)

  def saveLabels(self, filename):
    if self.labelFile:
      otherData = self.labelFile.otherData
    else:
      otherData = None
      imagename = self.imagePath
      
    lf = LabelFile()
    annotations = [utils.annotation_to_dict(item.annotation()) for item in self.annotList]
    flags = {}
    for i in range(self.flag_widget.count()):
      item = self.flag_widget.item(i)
      key = item.text()
      flag = item.checkState() == Qt.Checked
      flags[key] = flag
    try:
      imagePath = osp.relpath(self.imagePath, osp.dirname(filename))
      if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
        os.makedirs(osp.dirname(filename))
      lf.save(
        filename=filename,
        annotations=annotations,
        imagePath=imagePath,
        imageHeight=self.image.height(),
        imageWidth=self.image.width(),
        otherData = otherData,
        flags=flags,
      )
      
      self.labelFile = lf
      items = self.fileListWidget.findItems(
        self.imagePath, Qt.MatchExactly
      )
      if len(items) > 0:
        if len(items) != 1:
          raise RuntimeError("There are duplicate files.")
        items[0].setCheckState(Qt.Checked)
      # disable allows next and previous image to proceed
      # self.filename = filename
      return True
    except LabelFileError as e:
      self.errorMessage(
        self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
      )
      return False

  def toggleDrawMode(self, toggleAction):
    self.actions.movableMode.setChecked(False)
    edit=True
    createMode=self.action_to_shape[toggleAction]
    for action in self.actions.annotCheckableOperations:
      if action != toggleAction:
        action.setChecked(False)
      if action.isChecked():
        edit=False

    self.canvas.activeAction = toggleAction
    self.canvas.setEditing(edit)
    self.canvas.createMode = createMode
    if createMode == "polygon":
      for action in self.actions.exportSegMenu:
        action.setEnabled(True)
    elif createMode == "rectangle":
      for action in self.actions.exportDetectMenu:
        action.setEnabled(True)
    elif createMode == "circle":
      for action in self.actions.exportDetectMenu:
        action.setEnabled(True)

  def toggleMoveMode(self):
    move=False
    if self.actions.movableMode.isChecked():
      move=True
      for action in self.actions.annotCheckableOperations:
        action.setChecked(False)

    self.canvas.activeAction = self.actions.movableMode
    self.canvas.setMoving(move)

  def copySelectedAnnotation(self):
    added_annotations = self.canvas.copySelectedAnnotations()
    self.annotList.clearSelection()
    for annotation in added_annotations:
      self.addLabel(annotation)
    self.setDirty()

  def annotSelectionChanged(self):
    if self._noSelectionSlot:
      return

    selected_annotations = []
    for item in self.annotList.selectedItems():
      selected_annotations.append(item.annotation())
    if selected_annotations:
      self.canvas.selectAnnotations(selected_annotations)
    else:
      self.canvas.deSelectAnnotation()

  def annotItemChanged(self, item):
    annotation = item.annotation()
    self.canvas.setAnnotationVisible(annotation, item.checkState() == Qt.Checked)

  def annotOrderChanged(self):
    self.setDirty()
    self.canvas.loadAnnotations([item.annotation() for item in self.annotList])

  # Callback functions:
  def newAnnotation(self):
    """Pop-up and give focus to the label editor.

    position MUST be in global coordinates.
    """
    items = self.labelList.selectedItems()
    text = None
    if items:
      text = items[0].data(Qt.UserRole)
    flags = {}
    group_id = None
    if self.config["display_label_popup"] or not text:
      previous_text = self.labelDialog.edit.text()
      text, flags, group_id = self.labelDialog.popUp(text)
      if not text:
        self.labelDialog.edit.setText(previous_text)

    if text and not self.validateLabel(text):
      self.errorMessage(
        self.tr("Invalid label"),
        self.tr("Invalid label '{}' with validation type '{}'").format(
          text, self.config["validate_label"]
        ),
      )
      text = ""
    if text:
      self.annotList.clearSelection()
      annotation = self.canvas.setLastLabel(text, flags)
      annotation.group_id = group_id
      self.addLabel(annotation)
      self.actions.undoLastPoint.setEnabled(False)
      self.actions.undo.setEnabled(True)
      self.setDirty()
    else:
      self.canvas.undoLastLine()
      self.canvas.annotationsBackups.pop()

  def scrollRequest(self, delta, orientation):
    units = -delta * 0.1  # natural scroll
    bar = self.scrollBars[orientation]
    value = bar.value() + bar.singleStep() * units
    self.setScroll(orientation, value)

  def setScroll(self, orientation, value):
    self.scrollBars[orientation].setValue(value)
    self.scroll_values[orientation][self.filename] = value

  def setZoom(self, value):
    self.actions.fitWidth.setChecked(False)
    self.actions.fitWindow.setChecked(False)
    self.zoomMode = self.MANUAL_ZOOM
    self.zoomWidget.setValue(value)
    self.zoom_values[self.filename] = (self.zoomMode, value)

  def addZoom(self, increment=1.1):
    zoom_value = self.zoomWidget.value() * increment
    if increment > 1:
      zoom_value = math.ceil(zoom_value)
    else:
      zoom_value = math.floor(zoom_value)
    self.setZoom(zoom_value)

  def zoomRequest(self, delta, pos):
    canvas_width_old = self.canvas.width()
    units = 1.1
    if delta < 0:
      units = 0.9
    self.addZoom(units)

    canvas_width_new = self.canvas.width()
    if canvas_width_old != canvas_width_new:
      canvas_scale_factor = canvas_width_new / canvas_width_old

      x_shift = round(pos.x() * canvas_scale_factor) - pos.x()
      y_shift = round(pos.y() * canvas_scale_factor) - pos.y()

      self.setScroll(
        Qt.Horizontal,
        self.scrollBars[Qt.Horizontal].value() + x_shift,
      )
      self.setScroll(
        Qt.Vertical, self.scrollBars[Qt.Vertical].value() + y_shift,
      )

  def setFitWindow(self, value=True):
    if value:
      self.actions.fitWidth.setChecked(False)
    self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
    self.adjustScale()

  def setFitWidth(self, value=True):
    if value:
      self.actions.fitWindow.setChecked(False)
    self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
    self.adjustScale()

  def onAppearanceChangedCallback(self, brightness=1, contrast=1, show_pixelmap=None, show_groundtruth=None):
    if show_groundtruth is not None:
      self.canvas.show_groundtruth = show_groundtruth
      self.canvas.repaint()
      return

    img = utils.img_data_to_pil(self.imageData)
    if show_pixelmap:
      img = ImageEnhance.Brightness(img).enhance(0)
      self.canvas.show_pixelmap = True
    else:
      img = ImageEnhance.Brightness(img).enhance(brightness)
      img = ImageEnhance.Contrast(img).enhance(contrast)
      if show_pixelmap==False:
        self.canvas.show_pixelmap = False
      
    img_data = utils.img_pil_to_data(img)
    qimage = QtGui.QImage.fromData(img_data)
    self.canvas.loadPixmap(QtGui.QPixmap.fromImage(qimage))

  def togglePolygons(self, value):
    for item in self.annotList:
      item.setCheckState(Qt.Checked if value else Qt.Unchecked)

  def load_labelfile(self, imagename):
    label_file = self.getLabelFile(imagename)

    try:
      labelFile = LabelFile(label_file)
    except LabelFileError as e:
      self.errorMessage(
        self.tr("Error opening file"),
        self.tr(
          "<p><b>%s</b></p>"
          "<p>Make sure <i>%s</i> is a valid label file."
        )
        % (e, label_file),
      )
      self.status(self.tr("Error reading %s") % label_file)
      return False
    
    return labelFile

  def getAllAnnotations(self, imageList):
    annotations = []
    for imagename in imageList:
      label_file = self.getLabelFile(imagename)
      labelFile = self.load_labelfile(imagename)
      if labelFile == False: return False
      annotations.extend(labelFile.annotations)
    return annotations

  def loadFile(self, filename=None):
    """Load the specified file, or the last opened file if None."""
    # changing fileListWidget loads file
    if filename in self.imageList and self.fileListWidget.currentRow() != self.imageList.index(filename):
      self.fileListWidget.setCurrentRow(self.imageList.index(filename))
      self.fileListWidget.repaint()
      return

    if self.config["keep_prev"]:
      prev_annotations = self.canvas.annotations

    self.resetState()
    self.canvas.setEnabled(False)
    if filename is None:
      filename = self.settings.value("filename", "")
    filename = str(filename)
    if not QtCore.QFile.exists(filename):
      self.errorMessage(
        self.tr("Error opening file"),
        self.tr("No such file: <b>%s</b>") % filename,
      )
      return False
    # assumes same name, but json extension
    self.status(self.tr("Loading %s...") % osp.basename(str(filename)))
    label_file = self.getLabelFile(filename)
    if self.output_dir:
      label_file_without_path = osp.basename(label_file)
      label_file = osp.join(self.output_dir, label_file_without_path)
    
    if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
      self.labelFile = self.load_labelfile(filename)
      self.imagePath = filename
    
    self.imageData = LabelFile.load_image_file(filename)
    self.imagePath = filename

    if self.labelFile:
      imageList = [self.imagePath]
      if len(self.imageList) > 0:      imageList = self.imageList
      annotations = self.labelFile.annotations
      # bbox detection
      if all(annotation["shape_type"]=="rectangle" for annotation in annotations):
        for action in self.actions.exportDetectMenu:
          action.setEnabled(True)
      # segmentation
      elif any(annotation["shape_type"]=="polygon" for annotation in annotations):
        for action in self.actions.exportSegMenu:
          action.setEnabled(True)

    image = QtGui.QImage.fromData(self.imageData)

    if image.isNull():
      formats = [
        "*.{}".format(fmt.data().decode())
        for fmt in QtGui.QImageReader.supportedImageFormats()
      ]
      self.errorMessage(
        self.tr("Error opening file"),
        self.tr(
          "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
          "Supported image formats: {1}</p>"
        ).format(filename, ",".join(formats)),
      )
      self.status(self.tr("Error reading %s") % filename)
      return False
    self.image = image
    self.filename = filename
    flags = {k: False for k in self.config["flags"] or []}
    if self.labelFile:
      self.loadLabels(self.labelFile.annotations)
      if self.labelList.count() > 0:
        self.label_dock.raise_()
      else:
        flags.update(self.labelFile.flags)
        self.flag_dock.raise_()

    self.loadFlags(flags)
    if self.config["keep_prev"] and self.noAnnotations():
      self.loadAnnotations(prev_annotations, replace=False)
      self.setDirty()
    else:
      self.setClean()

    # set brightness constrast values
    brightness = self.appearance_widget.slider_brightness.value() / 50;
    contrast = self.appearance_widget.slider_contrast.value() / 50
    self.onAppearanceChangedCallback()
    self.canvas.setEnabled(True)

    if len(self.canvas.annotations) > 0:
      self.menus.export_.setEnabled(True)

    self.appearance_widget.setAnnotations(self.canvas.annotations)
    self.appearance_widget.setEnabled(True)

    # set zoom values
    is_initial_load = not self.zoom_values
    if self.filename in self.zoom_values:
      self.zoomMode = self.zoom_values[self.filename][0]
      self.setZoom(self.zoom_values[self.filename][1])
    elif is_initial_load or not self.config["keep_prev_scale"]:
      self.adjustScale(initial=True)
    # set scroll values
    for orientation in self.scroll_values:
      if self.filename in self.scroll_values[orientation]:
        self.setScroll(
          orientation, self.scroll_values[orientation][self.filename]
        )

    self.paintCanvas()
    self.addRecentFile(self.filename)
    self.toggleActions(True)
    self.status(self.tr("Loaded %s") % osp.basename(str(filename)))
    return True

  def resizeEvent(self, event):
    if (
      self.canvas
      and not self.image.isNull()
      and self.canvas.pixmap is not None
      and self.zoomMode != self.MANUAL_ZOOM
    ):
      self.adjustScale()
    super(MainWindow, self).resizeEvent(event)

  def paintCanvas(self):
    assert not self.image.isNull(), "cannot paint null image"
    self.canvas.scale = 0.01 * self.zoomWidget.value()
    self.canvas.adjustSize()
    self.canvas.update()

  def adjustScale(self, initial=False):
    value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
    value = int(100 * value)
    self.zoomWidget.setValue(value)
    self.zoom_values[self.filename] = (self.zoomMode, value)

  def scaleFitWindow(self):
    """Figure out the size of the pixmap to fit the main widget."""
    e = 2.0  # So that no scrollbars are generated.
    w1 = self.centralWidget().width() - e
    h1 = self.centralWidget().height() - e
    a1 = w1 / h1
    # Calculate a new scale value based on the pixmap's aspect ratio.
    w2 = self.canvas.pixmap.width() - 0.0
    h2 = self.canvas.pixmap.height() - 0.0
    a2 = w2 / h2
    return w1 / w2 if a2 >= a1 else h1 / h2

  def scaleFitWidth(self):
    # The epsilon does not seem to work too well here.
    w = self.centralWidget().width() - 2.0
    return w / self.canvas.pixmap.width()

  def enableSaveImageWithData(self, enabled):
    self.config["store_data"] = enabled

  def closeEvent(self, event):
    if not self.mayContinue():      event.ignore()

    if self.resetConfig:
      fname = self.settings.fileName()
      if osp.exists(fname):        os.remove(fname)
      self.resetConfig = False
    else:
      self.settings.setValue(
        "filename", self.filename if self.filename else ""
      )
      self.settings.setValue("window/size", self.size())
      self.settings.setValue("window/position", self.pos())
      self.settings.setValue("window/state", self.saveState())
      self.settings.setValue("recentFiles", self.recentFiles)
      
  def dragEnterEvent(self, event):
    extensions = [
      ".%s" % fmt.data().decode().lower()
      for fmt in QtGui.QImageReader.supportedImageFormats()
    ]
    if event.mimeData().hasUrls():
      items = [i.toLocalFile() for i in event.mimeData().urls()]
      if any([i.lower().endswith(tuple(extensions)) for i in items]):
        event.accept()
    else:
      event.ignore()

  def dropEvent(self, event):
    if not self.mayContinue():
      event.ignore()
      return
    items = [i.toLocalFile() for i in event.mimeData().urls()]
    self.importDroppedImageFiles(items)

  # User Dialogs #
  def loadRecent(self, filename):
    if self.mayContinue():
      self.loadFile(filename)

  def openPrevImg(self, _value=False):
    keep_prev = self.config["keep_prev"]
    if Qt.KeyboardModifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
      self.config["keep_prev"] = True

    if not self.mayContinue():
      return

    if len(self.imageList) <= 0:
      return

    if self.filename is None:
      return

    currIndex = self.imageList.index(self.filename)
    if currIndex - 1 >= 0:
      filename = self.imageList[currIndex - 1]
      if filename:
        self.loadFile(filename)
        if not self.labelFile or not len(self.labelFile.annotations) > 0:
          self.openPrevImg()

    self.config["keep_prev"] = keep_prev

  def openNextImg(self, _value=False, load=True):
    keep_prev = self.config["keep_prev"]
    if Qt.KeyboardModifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
      self.config["keep_prev"] = True

    if not self.mayContinue():
      return

    if len(self.imageList) <= 0:
      return

    filename = None
    if self.filename is None:
      filename = self.imageList[0]
    else:
      currIndex = self.imageList.index(self.filename)
      if currIndex + 1 < len(self.imageList):
        filename = self.imageList[currIndex + 1]
      else:
        filename = self.imageList[-1]
        if self.filename == filename:
          load = False
        
    self.filename = filename
    if self.filename and load:
      self.loadFile(self.filename)
      if not self.labelFile or not len(self.labelFile.annotations) > 0:
        self.openNextImg()

    self.config["keep_prev"] = keep_prev

  def openFile(self, _value=False):
    if not self.mayContinue():
      return
    path = osp.dirname(str(self.filename)) if self.filename else "."
    formats = [
      "*.{}".format(fmt.data().decode())
      for fmt in QtGui.QImageReader.supportedImageFormats()
    ]
    filters = self.tr("Image & Label files (%s)") % " ".join(formats)
    filename = QtWidgets.QFileDialog.getOpenFileName(
      self,
      self.tr("%s - Choose Image or Label file") % __appname__,
      path,
      filters,
    )
    if QT5:
      filename, _ = filename
    filename = str(filename)
    if filename:
      if filename not in self.imageList:
        self.fileListPath.clear()
        self.fileListWidget.clear()
      self.loadFile(filename)

  def saveFile(self, _value=False):
    assert not self.image.isNull(), "cannot save empty image"
    if self.labelFile:
      # DL20180323 - overwrite when in directory
      self._saveFile(self.labelFile.filename)
    elif self.output_file:
      self._saveFile(self.output_file)
      self.close()
    else:
      self._saveFile(self.saveFileDialog())

  def saveFileAs(self, _value=False):
    assert not self.image.isNull(), "cannot save empty image"
    self._saveFile(self.saveFileDialog())

  def saveFileDialog(self):
    caption = self.tr("%s - Choose File") % __appname__
    filters = self.tr("Label files (*%s)") % LabelFile.suffix
    if self.output_dir:
      dlg = QtWidgets.QFileDialog(
        self, caption, self.output_dir, filters
      )
    else:
      dlg = QtWidgets.QFileDialog(
        self, caption, self.currentPath(), filters
      )
    dlg.setDefaultSuffix(LabelFile.suffix[1:])
    dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
    dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
    dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
    basename = osp.basename(osp.splitext(self.filename)[0])
    if self.output_dir:
      default_label_file = osp.join(
        self.output_dir, basename + LabelFile.suffix
      )
    else:
      default_label_file = osp.join(
        self.currentPath(), basename + LabelFile.suffix
      )
    filename = dlg.getSaveFileName(
      self,
      self.tr("Choose File"),
      default_label_file,
      self.tr("Label files (*%s)") % LabelFile.suffix,
    )
    if isinstance(filename, tuple):
      filename, _ = filename
    return filename

  def _saveFile(self, filename):
    if filename and self.saveLabels(filename):
      self.setClean()

  def closeFileDir(self, _value=False):
    if not self.mayContinue():
      return
    self.resetState()
    self.setClean()
    self.fileListPath.clear()
    self.fileListWidget.clear()

    self.toggleActions(False)
    self.canvas.setEnabled(False)
    self.actions.saveAs.setEnabled(False)

  def getLabelFile(self, filename):
    if filename.lower().endswith(LabelFile.suffix):
      label_file = filename
    else:
      label_file = osp.splitext(filename)[0] + LabelFile.suffix
    return label_file

  def deleteFile(self):
    mb = QtWidgets.QMessageBox
    msg = self.tr(
      "You are about to permanently delete this label file, "
      "proceed anyway?"
    )
    answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
    if not answer == mb.Yes:      return

    label_file = self.getLabelFile(self.filename)
    if osp.exists(label_file):
      os.remove(label_file)
      logger.info("Label file is removed: {}".format(label_file))

      item = self.fileListWidget.currentItem()
      item.setCheckState(Qt.Unchecked)

      self.resetState()

  @Slot()
  def onChangeOutputDir(self, _value=False):
    default_output_dir = self.output_dir
    if default_output_dir is None and self.filename:
      default_output_dir = osp.dirname(self.filename)
    if default_output_dir is None:
      default_output_dir = self.currentPath()

    output_dir = QtWidgets.QFileDialog.getExistingDirectory(
      self,
      self.tr("%s - Save/Load Annotations in Directory") % __appname__,
      default_output_dir,
      QtWidgets.QFileDialog.ShowDirsOnly
      | QtWidgets.QFileDialog.DontResolveSymlinks,
    )
    output_dir = str(output_dir)

    if not output_dir:   return

    self.output_dir = output_dir
    self.statusBar().showMessage(
      self.tr("%s - Annotations will be saved/loaded in %s")
      % (__appname__, self.output_dir)
    )
    self.statusBar().show()

    current_filename = self.filename
    self.importDirImages(self.lastOpenDir, load=False)

    if current_filename in self.imageList:
      # retain currently selected file
      self.fileListWidget.setCurrentRow(
        self.imageList.index(current_filename)
      )
      self.fileListWidget.repaint()

  @Slot()
  def onChangeLanguage(self):
    languages = [self.tr(language) for language in self.support_languages]
    language, ok = QtWidgets.QInputDialog.getItem(self, self.tr('Select display language'),
                                      self.tr('List of languages'),
                                      languages,
                                       0, False)

    if not ok and language:      return

    mb = QtWidgets.QMessageBox
    msg = self.tr(
      "You are about to restart to change the language, "
      "proceed anyway?"
    )
    answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
    if not answer == mb.Yes:      return
    if languages.index(language) == 0:      return
    QtWidgets.QApplication.exit(MainWindow.RESTART_CODE + languages.index(language))

  @Slot()
  def onResetConfig(self):
    mb = QtWidgets.QMessageBox
    msg = self.tr(
      "Discard all changes in memory and reload everthing from file, "
      "proceed anyway?"
    )
    answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
    if not answer == mb.Yes:      return
    self.resetConfig = True
    QtWidgets.QApplication.exit(MainWindow.RESTART_CODE + MainWindow.RESET_CONFIG)

  @Slot()
  def onExportPixelMap(self):
    if not self.output_dir:   self.onChangeOutputDir()
    if not self.output_dir:   return False

    imageList = [self.imagePath]
    if len(self.imageList) > 0:
      mb = QtWidgets.QMessageBox
      msg = self.tr('File List exists. Do you want to export all files?')
      answer = mb.question(
        self,
        self.tr("Export all files"),
        msg,
        mb.Ok | mb.Cancel,
        mb.Ok,
      )
      if answer == mb.Ok:        imageList = self.imageList
    imageList_without_path = [osp.basename(image) for image in imageList]
    
    
    AnnotationType = ""
    annotations = self.getAllAnnotations(imageList)
    # bbox detection
    # if all(annotation["shape_type"]=="rectangle" for annotation in annotations):
    #   return False
    
    print("Creating pixel map:", self.output_dir)
    classes = {"__ignore__":-1, "_background_":0, }
    for annotation in annotations:
      class_name = annotation["label"]
      if class_name not in list(classes.keys()) + ["__ignore__", "_background_"]:
        classes[class_name] = len(classes)-1

    class_names = list(classes.keys())
    del class_names[0]

    if osp.isdir(osp.join(self.output_dir, "PixelMap")):
      shutil.rmtree(osp.join(self.output_dir, "PixelMap"))
    
    os.makedirs(osp.join(self.output_dir, "PixelMap"))
    
    colormap = imgviz.label_colormap()
    label_colordict = {label: dict(id=colormap[id].tolist()) for label, id in classes.items() if id>0}
    data = dict(
      version=__version__ ,
      images=imageList_without_path,
      labels=label_colordict,
    )
    try:
      filename = osp.join(self.output_dir, "PixelMap", "labels.json")
      with open(filename, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
      raise print(e)

    for imagename in imageList:
      base = osp.splitext(osp.basename(imagename))[0]
      out_img_file = osp.join(self.output_dir, "PixelMap", base + ".png")

      labelFile = self.load_labelfile(imagename)
      imageData = LabelFile.load_image_file(imagename)

      img = utils.img_data_to_arr(imageData)
      cls, ins = utils.annotations_to_label(
        img_shape=img.shape,
        annotations=labelFile.annotations,
        classes=classes,
      )
      ins[cls == -1] = 0  # ignore it.

      # class label
      utils.lblsave(out_img_file, cls)

  def exportDetectionVOC(self, imageList, classes):
    os.makedirs(osp.join(self.output_dir, "VOC"))
    os.makedirs(osp.join(self.output_dir, "VOC", "JPEGImages"))
    os.makedirs(osp.join(self.output_dir, "VOC", "Annotations"))
    os.makedirs(osp.join(self.output_dir, "VOC", "AnnotationsVisualization"))

    for imagename in imageList:
      base = osp.splitext(osp.basename(imagename))[0]
      out_img_file = osp.join(self.output_dir, "VOC", "JPEGImages", base + ".jpg")
      out_xml_file = osp.join(self.output_dir, "VOC", "Annotations", base + ".xml")
      out_viz_file = osp.join(self.output_dir, "VOC", "AnnotationsVisualization", base + ".jpg")

      labelFile = self.load_labelfile(imagename)
      imageData = LabelFile.load_image_file(imagename)

      img = utils.img_data_to_arr(imageData)
      imgviz.io.imsave(out_img_file, img)

      maker = lxml.builder.ElementMaker()
      xml = maker.annotation(
        maker.folder(),
        maker.filename(base + ".jpg"),
        maker.database(),  # e.g., The VOC2007 Database
        maker.annotation(),  # e.g., Pascal VOC2007
        maker.image(),  # e.g., flickr
        maker.size(
          maker.height(str(img.shape[0])),
          maker.width(str(img.shape[1])),
          maker.depth(str(img.shape[2])),
        ),
        maker.segmented(),
      )

      bboxes = []
      labels = []
      captions = []
      for annotation in labelFile.annotations:
        class_name = annotation["label"]
        class_id = classes[class_name]

        (xmin, ymin), (xmax, ymax) = annotation["points"]
        # swap if min is larger than max.
        xmin, xmax = sorted([xmin, xmax])
        ymin, ymax = sorted([ymin, ymax])

        bboxes.append([ymin, xmin, ymax, xmax])
        labels.append(class_id)
        captions.append(class_name)

        xml.append(
          maker.object(
            maker.name(annotation["label"]),
            maker.pose(),
            maker.truncated(),
            maker.difficult(),
            maker.bndbox(
              maker.xmin(str(xmin)),
              maker.ymin(str(ymin)),
              maker.xmax(str(xmax)),
              maker.ymax(str(ymax)),
            ),
          )
        )

      viz = imgviz.instances2rgb(
        image=img,
        labels=labels,
        bboxes=bboxes,
        captions=captions,
        font_size=15,
      )
      imgviz.io.imsave(out_viz_file, viz)

      with open(out_xml_file, "wb") as f:
        f.write(lxml.etree.tostring(xml, pretty_print=True))

  def exportSegmentationVOC(self, imageList, classes):
    os.makedirs(osp.join(self.output_dir, "VOC"))
    os.makedirs(osp.join(self.output_dir, "VOC", "JPEGImages"))
    os.makedirs(osp.join(self.output_dir, "VOC", "SegmentationClass"))
    os.makedirs(osp.join(self.output_dir, "VOC", "SegmentationClassPNG"))
    os.makedirs(osp.join(self.output_dir, "VOC", "SegmentationClassVisualization"))
    os.makedirs(osp.join(self.output_dir, "VOC", "SegmentationObject"))
    os.makedirs(osp.join(self.output_dir, "VOC", "SegmentationObjectPNG"))
    os.makedirs(osp.join(self.output_dir, "VOC", "SegmentationObjectVisualization"))

    class_names = list(classes.keys())
    del class_names[0]
    for imagename in imageList:
      base = osp.splitext(osp.basename(imagename))[0]
      out_img_file = osp.join(self.output_dir, "VOC", "JPEGImages", base + ".jpg")

      out_cls_file = osp.join(self.output_dir, "VOC", "SegmentationClass", base + ".npy")
      out_clsp_file = osp.join(self.output_dir, "VOC", "SegmentationClassPNG", base + ".png")
      out_clsv_file = osp.join(self.output_dir, "VOC", "SegmentationClassVisualization", base + ".jpg")

      out_ins_file = osp.join(self.output_dir, "VOC", "SegmentationObject", base + ".npy")
      out_insp_file = osp.join(self.output_dir, "VOC", "SegmentationObjectPNG", base + ".png")
      out_insv_file = osp.join(self.output_dir, "VOC", "SegmentationObjectVisualization", base + ".jpg")

      labelFile = self.load_labelfile(imagename)
      imageData = LabelFile.load_image_file(imagename)
      img = utils.img_data_to_arr(imageData)
      imgviz.io.imsave(out_img_file, img)

      cls, ins = utils.annotations_to_label(
        img_shape=img.shape,
        annotations=labelFile.annotations,
        classes=classes,
      )
      ins[cls == -1] = 0  # ignore it.

      # class label
      utils.lblsave(out_clsp_file, cls)
      np.save(out_cls_file, cls)
      clsv = imgviz.label2rgb(
        label=cls,
        img=imgviz.rgb2gray(img),
        label_names=class_names,
        font_size=15,
        loc="rb",
      )
      imgviz.io.imsave(out_clsv_file, clsv)

      # instance label
      utils.lblsave(out_insp_file, ins)
      np.save(out_ins_file, ins)
      instance_ids = np.unique(ins)
      instance_names = [str(i) for i in range(max(instance_ids) + 1)]
      insv = imgviz.label2rgb(
        label=ins,
        img=imgviz.rgb2gray(img),
        label_names=instance_names,
        font_size=15,
        loc="rb",
      )
      imgviz.io.imsave(out_insv_file, insv)

  @Slot()
  def onExportVOC(self):
    if not self.output_dir:   self.onChangeOutputDir()
    if not self.output_dir:   return False

    imageList = [self.imagePath]
    if len(self.imageList) > 0:
      mb = QtWidgets.QMessageBox
      msg = self.tr('File List exists. Do you want to export all files?')
      answer = mb.question(
        self,
        self.tr("Export all files"),
        msg,
        mb.Ok | mb.Cancel,
        mb.Ok,
      )
      if answer == mb.Ok:        imageList = self.imageList
    
    AnnotationType = ""
    annotations = self.getAllAnnotations(imageList)
    # bbox detection
    if all(annotation["shape_type"]=="rectangle" for annotation in annotations):
      AnnotationType = "bbox_detection"
    # segmentation
    elif any(annotation["shape_type"]=="polygon" for annotation in annotations):
      AnnotationType = "segmenation"

    print("Creating dataset VOC:", self.output_dir)
    classes = {"__ignore__":-1, "_background_":0, }
    for annotation in annotations:
      class_name = annotation["label"]
      if class_name not in list(classes.keys()) + ["__ignore__", "_background_"]:
        classes[class_name] = len(classes)-1

    if osp.isdir(osp.join(self.output_dir, "VOC")):
      shutil.rmtree(osp.join(self.output_dir, "VOC"))

    if AnnotationType == "bbox_detection":
      self.exportDetectionVOC(imageList, classes)
    elif AnnotationType == "segmenation":
      self.exportSegmentationVOC(imageList, classes)

  @Slot()
  def onExportCOCO(self):
    if not self.output_dir:   self.onChangeOutputDir()
    if not self.output_dir:   return False

    imageList = [self.imagePath]
    if len(self.imageList) > 0:
      mb = QtWidgets.QMessageBox
      msg = self.tr('File List exists. Do you want to export all files?')
      answer = mb.question(
        self,
        self.tr("Export all files"),
        msg,
        mb.Ok | mb.Cancel,
        mb.Ok,
      )
      if answer == mb.Ok:        imageList = self.imageList

    annotations = self.getAllAnnotations(imageList)
    # bbox detection
    if all(annotation["shape_type"]=="rectangle" for annotation in annotations):
      return False

    print("Creating dataset COCO:", self.output_dir)
    classes = {"__ignore__":-1, "_background_":0, }
    for annotation in annotations:
      class_name = annotation["label"]
      if class_name not in list(classes.keys()) + ["__ignore__", "_background_"]:
        classes[class_name] = len(classes)-1

    class_names = list(classes.keys())
    del class_names[0]

    if osp.isdir(osp.join(self.output_dir, "COCO")):
      shutil.rmtree(osp.join(self.output_dir, "COCO"))
    
    os.makedirs(osp.join(self.output_dir, "COCO"))
    os.makedirs(osp.join(self.output_dir, "COCO", "JPEGImages"))
    os.makedirs(osp.join(self.output_dir, "COCO", "Visualization"))
    
    now = datetime.datetime.now()
    data = dict(
      info=dict(
        description=None,
        url=None,
        version=None,
        year=now.year,
        contributor=None,
        date_created=now.strftime("%Y/%m/%d"),
      ),
      licenses=[dict(url=None, id=0, name=None,)],
      images=[
        # license, url, file_name, height, width, date_captured, id
      ],
      type="instances",
      annotations=[
        # segmentation, area, iscrowd, image_id, bbox, category_id, id
      ],
      categories=[
        # supercategory, id, name
      ],
    )

    out_ann_file = osp.join(self.output_dir, "COCO", "annotations.json")
    for image_id, imagename in enumerate(imageList):
      base = osp.splitext(osp.basename(imagename))[0]
      out_img_file = osp.join(self.output_dir, "COCO", "JPEGImages", base + ".jpg")
      out_viz_file = osp.join(self.output_dir, "COCO", "Visualization", base + ".jpg")

      labelFile = self.load_labelfile(imagename)
      imageData = LabelFile.load_image_file(imagename)
      img = utils.img_data_to_arr(imageData)
      imgviz.io.imsave(out_img_file, img)

      data["images"].append(
        dict(
          license=0,
          url=None,
          file_name=osp.relpath(out_img_file, osp.dirname(out_ann_file)),
          height=img.shape[0],
          width=img.shape[1],
          date_captured=None,
          id=image_id,
        )
      )

      masks = {}  # for area
      segmentations = collections.defaultdict(list)  # for segmentation
      for annotation in labelFile.annotations:
        points = annotation["points"]
        label = annotation["label"]
        group_id = annotation.get("group_id")
        shape_type = annotation.get("shape_type", "polygon")
        mask = utils.shape_to_mask(
          img.shape[:2], points, shape_type
        )

        if group_id is None:
          group_id = uuid.uuid1()

        instance = (label, group_id)

        if instance in masks:
          masks[instance] = masks[instance] | mask
        else:
          masks[instance] = mask

        if shape_type == "rectangle":
          (x1, y1), (x2, y2) = points
          x1, x2 = sorted([x1, x2])
          y1, y2 = sorted([y1, y2])
          points = [x1, y1, x2, y1, x2, y2, x1, y2]
        else:
          points = np.asarray(points).flatten().tolist()

        segmentations[instance].append(points)
      segmentations = dict(segmentations)

      for instance, mask in masks.items():
        class_name, group_id = instance
        if class_name not in class_names:
          continue
        class_id = classes[class_name]

        mask = np.asfortranarray(mask.astype(np.uint8))
        mask = cocomask.encode(mask)
        area = float(cocomask.area(mask))
        bbox = cocomask.toBbox(mask).flatten().tolist()

        data["annotations"].append(
          dict(
            id=len(data["annotations"]),
            image_id=image_id,
            category_id=class_id,
            segmentation=segmentations[instance],
            area=area,
            bbox=bbox,
            iscrowd=0,
          )
        )

      labels, captions, masks = zip(
        *[
          (classes[cnm], cnm, msk)
          for (cnm, gid), msk in masks.items()
          if cnm in class_names
        ]
      )
      viz = imgviz.instances2rgb(
        image=img,
        labels=labels,
        masks=masks,
        captions=captions,
        font_size=15,
        line_width=2,
      )
      imgviz.io.imsave(out_viz_file, viz)

      with open(out_ann_file, "w") as f:
        json.dump(data, f)
  
  # Message Dialogs. #
  def hasLabels(self):
    if self.noAnnotations():
      self.errorMessage(
        "No objects labeled",
        "You must label at least one object to save the file.",
      )
      return False
    return True

  def hasLabelFile(self):
    if self.filename is None:
      return False

    label_file = self.getLabelFile(self.filename)
    return osp.exists(label_file)

  def mayContinue(self):
    if not self.dirty:
      return True
    mb = QtWidgets.QMessageBox
    msg = self.tr('Save annotations to "{}" before closing?').format(
      self.filename
    )
    answer = mb.question(
      self,
      self.tr("Save annotations?"),
      msg,
      mb.Save | mb.Discard | mb.Cancel,
      mb.Save,
    )
    if answer == mb.Discard:
      return True
    elif answer == mb.Save:
      self.saveFile()
      return True
    else:  # answer == mb.Cancel
      return False

  def errorMessage(self, title, message):
    return QtWidgets.QMessageBox.critical(
      self, title, "<p><b>%s</b></p>%s" % (title, message)
    )

  def currentPath(self):
    return osp.dirname(str(self.filename)) if self.filename else "."

  def toggleKeepPrevMode(self):
    self.config["keep_prev"] = not self.config["keep_prev"]

  def onDeleteSelectedAnnotation(self):
    yes, no = QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No
    msg = self.tr(
      "You are about to permanently delete {} polygons, "
      "proceed anyway?"
    ).format(len(self.canvas.selectedAnnotations))
    if yes == QtWidgets.QMessageBox.warning(
      self, self.tr("Attention"), msg, yes | no, yes
    ):
      self.remLabels(self.canvas.deleteSelected())
      self.setDirty()
      if self.noAnnotations():
        for action in self.actions.onAnnotationsPresent:
          action.setEnabled(False)

  def copyAnnotation(self):
    self.canvas.endMove(copy=True)
    self.annotList.clearSelection()
    for annotation in self.canvas.selectedAnnotations:
      self.addLabel(annotation)
    self.setDirty()

  def moveAnnotation(self):
    self.canvas.endMove(copy=False)
    self.setDirty()

  def openDirDialog(self, _value=False, dirpath=None):
    defaultOpenDirPath = dirpath if dirpath else "."
    if self.lastOpenDir and osp.exists(self.lastOpenDir):
      defaultOpenDirPath = self.lastOpenDir
    else:
      defaultOpenDirPath = (
        osp.dirname(self.filename) if self.filename else "."
      )

    targetDirPath = str(
      QtWidgets.QFileDialog.getExistingDirectory(
        self,
        self.tr("%s - Open Directory") % __appname__,
        defaultOpenDirPath,
        QtWidgets.QFileDialog.ShowDirsOnly
        | QtWidgets.QFileDialog.DontResolveSymlinks,
      )
    )
    self.importDirImages(targetDirPath)

  @property
  def imageList(self):
    list = []
    for i in range(self.fileListWidget.count()):
      item = self.fileListWidget.item(i)
      list.append(osp.join(self.lastOpenDir, item.text()))
    return list

  def importDroppedImageFiles(self, imageFiles):
    extensions = [
      ".%s" % fmt.data().decode().lower()
      for fmt in QtGui.QImageReader.supportedImageFormats()
    ]
  
    self.lastOpenDir = None
    self.filename = None
    self.fileListWidget.clear()
    for file in imageFiles:
      if file in self.imageList or not file.lower().endswith(
        tuple(extensions)
      ):
        continue
      label_file = self.getLabelFile(file)
      if self.output_dir:
        label_file_without_path = osp.basename(label_file)
        label_file = osp.join(self.output_dir, label_file_without_path)
      item = QtWidgets.QListWidgetItem(osp.basename(file))
      item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
      if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
        item.setCheckState(Qt.Checked)
      else:
        item.setCheckState(Qt.Unchecked)
      self.fileListWidget.addItem(item)

      if self.lastOpenDir is None:
        self.lastOpenDir = osp.dirname(file)

    if len(self.imageList) > 1:
      self.actions.openNextImg.setEnabled(True)
      self.actions.openPrevImg.setEnabled(True)

    self.openNextImg()

  def importDirImages(self, dirpath, pattern=None, load=True):
    if not self.mayContinue() or not dirpath:
      return

    self.setClean()
    self.actions.openNextImg.setEnabled(True)
    self.actions.openPrevImg.setEnabled(True)

    self.fileListPath.setText(dirpath)
    self.lastOpenDir = dirpath
    self.filename = None
    self.fileListWidget.clear()
    for filename in utils.scan_all_images(dirpath):
      if pattern and pattern not in filename:
        continue
      label_file = self.getLabelFile(filename)
      if self.output_dir:
        label_file_without_path = osp.basename(label_file)
        label_file = osp.join(self.output_dir, label_file_without_path)
      item = QtWidgets.QListWidgetItem(osp.basename(filename))
      item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
      if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
        item.setCheckState(Qt.Checked)
      else:
        item.setCheckState(Qt.Unchecked)
      self.fileListWidget.addItem(item)

    self.openNextImg(load=load)
