# -*- coding: utf-8 -*-

import functools
import math
import os
import os.path as osp
import shutil
import re
import webbrowser

import lxml.builder
import lxml.etree

import imgviz
from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets

from labelme import __appname__
from labelme import PY2
from labelme import QT5

from . import utils
from labelme.config import get_config
from labelme.label_file import LabelFile
from labelme.label_file import LabelFileError
from labelme.logger import logger
from labelme.annotation import Annotation
from labelme.widgets import BrightnessContrastDialog
from labelme.widgets import Canvas
from labelme.widgets import LabelDialog
from labelme.widgets import AnnotationListWidget
from labelme.widgets import AnnotationListWidgetItem
from labelme.widgets import ToolBar
from labelme.widgets import LabelQListWidget
from labelme.widgets import ZoomWidget


# FIXME
# - [medium] Set max zoom value to something big enough for FitWidth/Window

# TODO(unknown):
# - [high] Add polygon movement with arrow keys
# - [high] Deselect annotation when clicking and already selected(?)
# - [low,maybe] Preview images on file dialogs.
# - Zoom is too "steppy".


LABEL_COLORMAP = imgviz.label_colormap(value=200)
class MainWindow(QtWidgets.QMainWindow):

  FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2
  RESTART_CODE = 0x1234

  def __init__(
    self,
    support_language,
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

    # see labelme/config/default_config.yaml for valid configuration
    if config is None:
      config = get_config()
    self._config = config
    self.support_language = support_language

    # set default annotation colors
    Annotation.line_color = QtGui.QColor(*self._config["annotation"]["line_color"])
    Annotation.fill_color = QtGui.QColor(*self._config["annotation"]["fill_color"])
    Annotation.select_line_color = QtGui.QColor(
      *self._config["annotation"]["select_line_color"]
    )
    Annotation.select_fill_color = QtGui.QColor(
      *self._config["annotation"]["select_fill_color"]
    )
    Annotation.vertex_fill_color = QtGui.QColor(
      *self._config["annotation"]["vertex_fill_color"]
    )
    Annotation.hvertex_fill_color = QtGui.QColor(
      *self._config["annotation"]["hvertex_fill_color"]
    )

    super(MainWindow, self).__init__()
    self.setWindowTitle(__appname__)

    # Whether we need to save or not.
    self.dirty = False

    self._noSelectionSlot = False

    # Main widgets and related state.
    self.labelDialog = LabelDialog(
      parent=self,
      labels=self._config["labels"],
      sort_labels=self._config["sort_labels"],
      show_text_field=self._config["show_label_text_field"],
      completion=self._config["label_completion"],
      fit_to_content=self._config["fit_to_content"],
      flags=self._config["label_flags"],
    )

    self.fileSearch = QtWidgets.QLineEdit()
    self.fileSearch.setPlaceholderText(self.tr("Search Filename"))
    self.fileSearch.textChanged.connect(self.fileSearchChanged)
    self.fileListWidget = QtWidgets.QListWidget()
    self.fileListWidget.itemSelectionChanged.connect(
      self.fileSelectionChanged
    )
    fileListLayout = QtWidgets.QVBoxLayout()
    fileListLayout.setContentsMargins(0, 0, 0, 0)
    fileListLayout.setSpacing(0)
    fileListLayout.addWidget(self.fileSearch)
    fileListLayout.addWidget(self.fileListWidget)
    self.file_dock = QtWidgets.QDockWidget(self.tr(u"File List"), self)
    self.file_dock.setObjectName(u"Files")
    fileListWidget = QtWidgets.QWidget()
    fileListWidget.setLayout(fileListLayout)
    self.file_dock.setWidget(fileListWidget)

    self.lastOpenDir = None

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
    if self._config["labels"]:
      for label in self._config["labels"]:
        item = self.labelList.createItemFromLabel(label)
        self.labelList.addItem(item)
        rgb = self._get_rgb_by_label(label)
        self.labelList.setItemLabel(item, label, rgb)
    self.label_dock = QtWidgets.QDockWidget(self.tr(u"Label List"), self)
    self.label_dock.setObjectName(u"Label List")
    self.label_dock.setWidget(self.labelList)

    self.annotList = AnnotationListWidget()
    self.annotList.itemSelectionChanged.connect(self.annotSelectionChanged)
    self.annotList.itemDoubleClicked.connect(self.editAnnot)
    self.annotList.itemChanged.connect(self.annotItemChanged)
    self.annotList.itemDropped.connect(self.annotOrderChanged)
    self.annot_dock = QtWidgets.QDockWidget(self.tr("Annotation List"), self)
    self.annot_dock.setObjectName(u"Annotations")
    self.annot_dock.setWidget(self.annotList)

    self.zoomWidget = ZoomWidget()
    self.setAcceptDrops(True)

    self.canvas = self.annotList.canvas = Canvas(
      epsilon=self._config["epsilon"],
      double_click=self._config["canvas"]["double_click"],
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
    for dock in ["file_dock", "flag_dock", "label_dock", "annot_dock"]:
      if self._config[dock]["closable"]:
        features = features | QtWidgets.QDockWidget.DockWidgetClosable
      if self._config[dock]["floatable"]:
        features = features | QtWidgets.QDockWidget.DockWidgetFloatable
      if self._config[dock]["movable"]:
        features = features | QtWidgets.QDockWidget.DockWidgetMovable
      getattr(self, dock).setFeatures(features)
      if self._config[dock]["show"] is False:
        getattr(self, dock).setVisible(False)

    self.addDockWidget(Qt.LeftDockWidgetArea, self.file_dock)
    self.addDockWidget(Qt.RightDockWidgetArea, self.flag_dock)
    self.addDockWidget(Qt.RightDockWidgetArea, self.label_dock)
    self.addDockWidget(Qt.RightDockWidgetArea, self.annot_dock)

    # Actions
    action = functools.partial(utils.newAction, self)
    shortcuts = self._config["shortcuts"]
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
      self.tr("&Next Image"),
      self.openNextImg,
      shortcuts["open_next"],
      "next",
      self.tr(u"Open next (hold Ctl+Shift to copy labels)"),
      enabled=False,
    )
    openPrevImg = action(
      self.tr("&Prev Image"),
      self.openPrevImg,
      shortcuts["open_prev"],
      "prev",
      self.tr(u"Open prev (hold Ctl+Shift to copy labels)"),
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
    saveAuto.setChecked(self._config["auto_save"])

    saveWithImageData = action(
      text=self.tr("Save With Image Data"),
      slot=self.enableSaveImageWithData,
      tip=self.tr("Save image data in label file"),
      checkable=True,
      checked=self._config["store_data"],
    )

    changeOutputDir = action(
      self.tr("Change &Output Dir"),
      slot=self.onChangeOutputDir,
      shortcut=shortcuts["save_to"],
      icon="open",
      tip=self.tr(u"Change where annotations are loaded/saved"),
    )
    
    changeLanguage = action(
      self.tr("Change &Language"),
      slot=self.onChangeLanguage,
      icon="translate",
      tip=self.tr(u"Change display language"),
    )

    close = action(
      self.tr("&Close"),
      self.closeFile,
      shortcuts["close"],
      "close",
      self.tr("Close current file"),
    )

    toggle_keep_prev_mode = action(
      self.tr("Keep Previous Annotation"),
      self.toggleKeepPrevMode,
      shortcuts["toggle_keep_prev_mode"],
      None,
      self.tr('Toggle "keep pevious annotation" mode'),
      checkable=True,
    )
    toggle_keep_prev_mode.setChecked(self._config["keep_prev"])

    createMode = action(
      self.tr("Create Polygons"),
      lambda: self.toggleDrawMode(False, createMode="polygon"),
      shortcuts["create_polygon"],
      "objects",
      self.tr("Start drawing polygons"),
      enabled=False,
    )
    createRectangleMode = action(
      self.tr("Create Rectangle"),
      lambda: self.toggleDrawMode(False, createMode="rectangle"),
      shortcuts["create_rectangle"],
      "objects",
      self.tr("Start drawing rectangles"),
      enabled=False,
    )
    createCircleMode = action(
      self.tr("Create Circle"),
      lambda: self.toggleDrawMode(False, createMode="circle"),
      shortcuts["create_circle"],
      "objects",
      self.tr("Start drawing circles"),
      enabled=False,
    )
    createLineMode = action(
      self.tr("Create Line"),
      lambda: self.toggleDrawMode(False, createMode="line"),
      shortcuts["create_line"],
      "objects",
      self.tr("Start drawing lines"),
      enabled=False,
    )
    createPointMode = action(
      self.tr("Create Point"),
      lambda: self.toggleDrawMode(False, createMode="point"),
      shortcuts["create_point"],
      "objects",
      self.tr("Start drawing points"),
      enabled=False,
    )
    createLineStripMode = action(
      self.tr("Create LineStrip"),
      lambda: self.toggleDrawMode(False, createMode="linestrip"),
      shortcuts["create_linestrip"],
      "objects",
      self.tr("Start drawing linestrip (Ctrl+LeftClick ends creation)"),
      enabled=False,
    )

    editMode = action(
      text=self.tr("Edit Annotations"),
      slot=self.onEditAnnotation,
      shortcut=shortcuts["edit_annotation"],
      icon="edit",
      tip=self.tr("Move and edit the selected annotations"),
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
    copy = action(
      text=self.tr("Duplicate Annotations"),
      slot=self.copySelectedAnnotation,
      shortcut=shortcuts["duplicate_annotation"],
      icon="copy",
      tip=self.tr("Create a duplicate of the selected annotations"),
      enabled=False,
    )
    undoLastPoint = action(
      self.tr("Undo last point"),
      self.canvas.undoLastPoint,
      shortcuts["undo_last_point"],
      "undo",
      self.tr("Undo last drawn point"),
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
      text="Remove Selected Point",
      slot=self.canvas.removeSelectedPoint,
      icon="edit",
      tip="Remove selected point from polygon",
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
    brightnessContrast = action(
      self.tr("&Brightness Contrast"),
      self.brightnessContrast,
      None,
      "color",
      self.tr("Adjust brightness and contrast"),
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

    edit = action(
      self.tr("&Edit Label"),
      self.editAnnot,
      shortcuts["edit_label"],
      "edit",
      self.tr("Modify the label of the selected polygon"),
      enabled=False,
    )

    fill_drawing = action(
      self.tr("Fill Drawing Polygon"),
      self.canvas.setFillDrawing,
      None,
      "color",
      self.tr("Fill polygon while drawing"),
      checkable=True,
      enabled=True,
    )
    fill_drawing.trigger()

    exportPixel = action(
      "Pixel",
      slot=self.onExportPixel,
      icon="export",
      tip=self.tr("Export pixel labeling"),
    )

    exportVOC = action(
      "VOC",
      slot=self.onExportVOC,
      icon="export",
      tip=self.tr("Export VOC dataset format"),
    )

    exportCOCO = action(
      "COCO",
      slot=self.onExportCOCO,
      icon="export",
      tip=self.tr("Export COCO dataset format"),
    )

    importPixel = action(
      "Pixel",
      slot=self.onImportPixel,
      icon="import",
      tip=self.tr("Import pixel labeling"),
    )

    importVOC = action(
      "VOC",
      slot=self.onImportVOC,
      icon="import",
      tip=self.tr("Import VOC dataset format"),
    )

    importCOCO = action(
      "COCO",
      slot=self.onImportCOCO,
      icon="import",
      tip=self.tr("Import COCO dataset format"),
    )

    #self.actions.exportPixel.setEnabled(True)

    # Lavel list context menu.
    labelMenu = QtWidgets.QMenu()
    utils.addActions(labelMenu, (edit, delete))
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
      edit=edit,
      copy=copy,
      undoLastPoint=undoLastPoint,
      undo=undo,
      addPointToEdge=addPointToEdge,
      removePoint=removePoint,
      createMode=createMode,
      editMode=editMode,
      createRectangleMode=createRectangleMode,
      createCircleMode=createCircleMode,
      createLineMode=createLineMode,
      createPointMode=createPointMode,
      createLineStripMode=createLineStripMode,
      zoom=zoom,
      zoomIn=zoomIn,
      zoomOut=zoomOut,
      zoomOrg=zoomOrg,
      fitWindow=fitWindow,
      fitWidth=fitWidth,
      brightnessContrast=brightnessContrast,
      zoomActions=zoomActions,
      openNextImg=openNextImg,
      openPrevImg=openPrevImg,
      fileMenuActions=(open_, opendir, save, saveAs, close, quit),
      tool=(),
      # XXX: need to add some actions here to activate the shortcut
      editMenu=(
        edit,
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
        createMode,
        createRectangleMode,
        createCircleMode,
        createLineMode,
        createPointMode,
        createLineStripMode,
        editMode,
        edit,
        copy,
        delete,
        undo,
        undoLastPoint,
        addPointToEdge,
        removePoint,
      ),
      onLoadActive=(
        close,
        createMode,
        createRectangleMode,
        createCircleMode,
        createLineMode,
        createPointMode,
        createLineStripMode,
        editMode,
        brightnessContrast,
      ),
      onAnnotationsPresent=(saveAs, hideAll, showAll),
      exportMenu=(
        exportPixel,
        exportVOC,
        exportCOCO,
      ),
      importMenu=(
        importPixel,
        importVOC,
        importCOCO,
      ),
    )

    self.canvas.edgeSelected.connect(self.canvasAnnotationEdgeSelected)
    self.canvas.vertexSelected.connect(self.actions.removePoint.setEnabled)

    self.menus = utils.struct(
      file=self.menu(self.tr("&File")),
      edit=self.menu(self.tr("&Edit")),
      data=self.menu(self.tr("&Dataset")),
      view=self.menu(self.tr("&View")),
      help=self.menu(self.tr("&Help")),
      recentFiles=QtWidgets.QMenu(self.tr("Open &Recent")),
      preferences=QtWidgets.QMenu(self.tr("&Preferences")),
      export_=QtWidgets.QMenu(self.tr("&Export")),
      import_=QtWidgets.QMenu(self.tr("&Import")),
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
      ),
    )

    utils.addActions(
      self.menus.data,
      (
        self.menus.export_,
        self.menus.import_,
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

    utils.addActions(
      self.menus.import_,
      (
        importPixel,
        importVOC,
        importCOCO,
      ),
    )

    utils.addActions(
      self.menus.view,
      (
        self.flag_dock.toggleViewAction(),
        self.label_dock.toggleViewAction(),
        self.annot_dock.toggleViewAction(),
        self.file_dock.toggleViewAction(),
        None,
        fill_drawing,
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
        brightnessContrast,
      ),
    )

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

    self.tools = self.toolbar("Tools")
    # Menu buttons on Left
    self.actions.tool = (
      open_,
      opendir,
      openNextImg,
      openPrevImg,
      save,
      deleteFile,
      None,
      createMode,
      editMode,
      copy,
      delete,
      undo,
      brightnessContrast,
      None,
      zoom,
      fitWidth,
    )

    self.statusBar().showMessage(self.tr("%s started.") % __appname__)
    self.statusBar().show()

    if output_file is not None and self._config["auto_save"]:
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
    self.otherData = None
    self.zoom_level = 100
    self.fit_window = False
    self.zoom_values = {}  # key=filename, value=(zoom_mode, zoom_value)
    self.brightnessContrast_values = {}
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
    self.settings = QtCore.QSettings("labelme", "labelme")
    # FIXME: QSettings.value can return None on PyQt4
    self.recentFiles = self.settings.value("recentFiles", []) or []
    size = self.settings.value("window/size", QtCore.QSize(600, 500))
    position = self.settings.value("window/position", QtCore.QPoint(0, 0))
    self.resize(size)
    self.move(position)
    # or simply:
    # self.restoreGeometry(settings['window/geometry']
    self.restoreState(
      self.settings.value("window/state", QtCore.QByteArray())
    )

    # Populate the File menu dynamically.
    self.updateFileMenu()
    # Since loading the file may take some time,
    # make sure it runs in the background.
    if self.filename is not None:
      self.queueEvent(functools.partial(self.loadFile, self.filename))

    # Callbacks:
    self.zoomWidget.valueChanged.connect(self.paintCanvas)

    self.populateModeActions()

    # self.firstStart = True
    # if self.firstStart:
    #  QWhatsThis.enterWhatsThisMode()
  def menu(self, title, actions=None):
    menu = self.menuBar().addMenu(title)
    if actions:
      utils.addActions(menu, actions)
    return menu

  def toolbar(self, title, actions=None):
    toolbar = ToolBar(title)
    toolbar.setObjectName("%sToolBar" % title)
    # toolbar.setOrientation(Qt.Vertical)
    toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    if actions:
      utils.addActions(toolbar, actions)
    self.addToolBar(Qt.LeftToolBarArea, toolbar)
    return toolbar

  # Support Functions

  def noAnnotations(self):
    return not len(self.annotList)

  def populateModeActions(self):
    tool, menu = self.actions.tool, self.actions.menu
    self.tools.clear()
    utils.addActions(self.tools, tool)
    self.canvas.menus[0].clear()
    utils.addActions(self.canvas.menus[0], menu)
    self.menus.edit.clear()
    actions = (
      self.actions.createMode,
      self.actions.createRectangleMode,
      self.actions.createCircleMode,
      self.actions.createLineMode,
      self.actions.createPointMode,
      self.actions.createLineStripMode,
      self.actions.editMode,
    )
    utils.addActions(self.menus.edit, actions + self.actions.editMenu)

  def setDirty(self):
    if self._config["auto_save"] or self.actions.saveAuto.isChecked():
      label_file = osp.splitext(self.imagePath)[0] + ".json"
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
    self.actions.createMode.setEnabled(True)
    self.actions.createRectangleMode.setEnabled(True)
    self.actions.createCircleMode.setEnabled(True)
    self.actions.createLineMode.setEnabled(True)
    self.actions.createPointMode.setEnabled(True)
    self.actions.createLineStripMode.setEnabled(True)
    title = __appname__
    if self.filename is not None:
      title = "{} - {}".format(title, self.filename)
    self.setWindowTitle(title)

    if self.hasLabelFile():
      self.actions.deleteFile.setEnabled(True)
    else:
      self.actions.deleteFile.setEnabled(False)

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
    self.labelList.clear()
    self.annotList.clear()
    self.filename = None
    self.imagePath = None
    self.imageData = None
    self.labelFile = None
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

  # Callbacks

  def undoAnnotationEdit(self):
    self.canvas.restoreAnnotation()
    self.annotList.clear()
    self.loadAnnotations(self.canvas.annotations)
    self.actions.undo.setEnabled(self.canvas.isAnnotationRestorable)

  def tutorial(self):
    url = "https://github.com/codebaragi23/labelme/tree/master/examples/tutorial"  # NOQA
    webbrowser.open(url)

  def toggleDrawingSensitive(self, drawing=True):
    """Toggle drawing sensitive.

    In the middle of drawing, toggling between modes should be disabled.
    """
    self.actions.editMode.setEnabled(not drawing)
    self.actions.undoLastPoint.setEnabled(drawing)
    self.actions.undo.setEnabled(not drawing)
    self.actions.delete.setEnabled(not drawing)

  def toggleDrawMode(self, edit=True, createMode="polygon"):
    self.canvas.setEditing(edit)
    self.canvas.createMode = createMode
    if edit:
      self.actions.createMode.setEnabled(True)
      self.actions.createRectangleMode.setEnabled(True)
      self.actions.createCircleMode.setEnabled(True)
      self.actions.createLineMode.setEnabled(True)
      self.actions.createPointMode.setEnabled(True)
      self.actions.createLineStripMode.setEnabled(True)
    else:
      if createMode == "polygon":
        self.actions.createMode.setEnabled(False)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
      elif createMode == "rectangle":
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(False)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
      elif createMode == "line":
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(False)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
      elif createMode == "point":
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(False)
        self.actions.createLineStripMode.setEnabled(True)
      elif createMode == "circle":
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(False)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
      elif createMode == "linestrip":
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(False)
      else:
        raise ValueError("Unsupported createMode: %s" % createMode)
    self.actions.editMode.setEnabled(not edit)

  def onEditAnnotation(self):
    self.toggleDrawMode(True)

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
    self.menus.labelList.exec_(self.annotList.mapToGlobal(point))

  def validateLabel(self, label):
    # no validation
    if self._config["validate_label"] is None:
      return True

    for i in range(self.labelList.count()):
      label_i = self.labelList.item(i).data(Qt.UserRole)
      if self._config["validate_label"] in ["exact"]:
        if label_i == label:
          return True
    return False

  def editAnnot(self, item=None):
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
          text, self._config["validate_label"]
        ),
      )
      return
    annotation.label = text
    annotation.flags = flags
    annotation.group_id = group_id
    if annotation.group_id is None:
      item.setText(annotation.label)
    else:
      item.setText("{} ({})".format(annotation.label, annotation.group_id))
    self.setDirty()
    if not self.labelList.findItemsByLabel(annotation.label):
      item = QtWidgets.QListWidgetItem()
      item.setData(Qt.UserRole, annotation.label)
      self.labelList.addItem(item)

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

    currIndex = self.imageList.index(str(item.text()))
    if currIndex < len(self.imageList):
      filename = self.imageList[currIndex]
      if filename:
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
    annotation.line_color = QtGui.QColor(r, g, b)
    annotation.vertex_fill_color = QtGui.QColor(r, g, b)
    annotation.hvertex_fill_color = QtGui.QColor(255, 255, 255)
    annotation.fill_color = QtGui.QColor(r, g, b, 128)
    annotation.select_line_color = QtGui.QColor(255, 255, 255)
    annotation.select_fill_color = QtGui.QColor(r, g, b, 155)

  def _get_rgb_by_label(self, label):
    if self._config["annotation_color"] == "auto":
      item = self.labelList.findItemsByLabel(label)[0]
      label_id = self.labelList.indexFromItem(item).row() + 1
      label_id += self._config["shift_auto_annotation_color"]
      return LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)]
    elif (
      self._config["annotation_color"] == "manual"
      and self._config["label_colors"]
      and label in self._config["label_colors"]
    ):
      return self._config["label_colors"][label]
    elif self._config["default_annotation_color"]:
      return self._config["default_annotation_color"]

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

  def loadLabels(self, annotations):
    annot = []
    for annotation in annotations:
      label = annotation["label"]
      points = annotation["points"]
      shape_type = annotation["shape_type"]
      flags = annotation["flags"]
      group_id = annotation["group_id"]
      other_data = annotation["other_data"]

      annotation = Annotation(
        label=label, shape_type=shape_type, group_id=group_id,
      )
      for x, y in points:
        annotation.addPoint(QtCore.QPointF(x, y))
      annotation.close()

      default_flags = {}
      if self._config["label_flags"]:
        for pattern, keys in self._config["label_flags"].items():
          if re.match(pattern, label):
            for key in keys:
              default_flags[key] = False
      annotation.flags = default_flags
      annotation.flags.update(flags)
      annotation.other_data = other_data

      annot.append(annotation)
    self.loadAnnotations(annot)

  def loadFlags(self, flags):
    self.flag_widget.clear()
    for key, flag in flags.items():
      item = QtWidgets.QListWidgetItem(key)
      item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
      item.setCheckState(Qt.Checked if flag else Qt.Unchecked)
      self.flag_widget.addItem(item)

  def format_annotation(self, s):
    data = s.other_data.copy()
    data.update(
      dict(
        label=s.label.encode("utf-8") if PY2 else s.label,
        points=[(p.x(), p.y()) for p in s.points],
        group_id=s.group_id,
        shape_type=s.shape_type,
        flags=s.flags,
      )
    )
    return data

  def saveLabels(self, filename):
    lf = LabelFile()

    annotations = [self.format_annotation(item.annotation()) for item in self.annotList]
    flags = {}
    for i in range(self.flag_widget.count()):
      item = self.flag_widget.item(i)
      key = item.text()
      flag = item.checkState() == Qt.Checked
      flags[key] = flag
    try:
      imagePath = osp.relpath(self.imagePath, osp.dirname(filename))
      imageData = self.imageData if self._config["store_data"] else None
      if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
        os.makedirs(osp.dirname(filename))
      lf.save(
        filename=filename,
        annotations=annotations,
        imagePath=imagePath,
        imageData=imageData,
        imageHeight=self.image.height(),
        imageWidth=self.image.width(),
        otherData=self.otherData,
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

  def copySelectedAnnotation(self):
    added_annotations = self.canvas.copySelectedAnnotations()
    self.annotList.clearSelection()
    for annotation in added_annotations:
      self.addLabel(annotation)
    self.setDirty()

  def annotSelectionChanged(self):
    if self._noSelectionSlot:
      return
    if self.canvas.editing():
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
    if self._config["display_label_popup"] or not text:
      previous_text = self.labelDialog.edit.text()
      text, flags, group_id = self.labelDialog.popUp(text)
      if not text:
        self.labelDialog.edit.setText(previous_text)

    if text and not self.validateLabel(text):
      self.errorMessage(
        self.tr("Invalid label"),
        self.tr("Invalid label '{}' with validation type '{}'").format(
          text, self._config["validate_label"]
        ),
      )
      text = ""
    if text:
      self.annotList.clearSelection()
      annotation = self.canvas.setLastLabel(text, flags)
      annotation.group_id = group_id
      self.addLabel(annotation)
      self.actions.editMode.setEnabled(True)
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

  def onNewBrightnessContrast(self, qimage):
    self.canvas.loadPixmap(
      QtGui.QPixmap.fromImage(qimage), clear_annotations=False
    )

  def brightnessContrast(self, value):
    dialog = BrightnessContrastDialog(
      utils.img_data_to_pil(self.imageData),
      self.onNewBrightnessContrast,
      parent=self,
    )
    brightness, contrast = self.brightnessContrast_values.get(
      self.filename, (None, None)
    )
    if brightness is not None:
      dialog.slider_brightness.setValue(brightness)
    if contrast is not None:
      dialog.slider_contrast.setValue(contrast)
    dialog.exec_()

    brightness = dialog.slider_brightness.value()
    contrast = dialog.slider_contrast.value()
    self.brightnessContrast_values[self.filename] = (brightness, contrast)

  def togglePolygons(self, value):
    for item in self.annotList:
      item.setCheckState(Qt.Checked if value else Qt.Unchecked)

  def loadFile(self, filename=None):
    """Load the specified file, or the last opened file if None."""
    # changing fileListWidget loads file
    if filename in self.imageList and (
      self.fileListWidget.currentRow() != self.imageList.index(filename)
    ):
      self.fileListWidget.setCurrentRow(self.imageList.index(filename))
      self.fileListWidget.repaint()
      return

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
    label_file = osp.splitext(filename)[0] + ".json"
    if self.output_dir:
      label_file_without_path = osp.basename(label_file)
      label_file = osp.join(self.output_dir, label_file_without_path)
    if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(
      label_file
    ):
      try:
        self.labelFile = LabelFile(label_file)
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
      self.imageData = self.labelFile.imageData
      self.imagePath = osp.join(
        osp.dirname(label_file), self.labelFile.imagePath,
      )
      self.otherData = self.labelFile.otherData
    else:
      self.imageData = LabelFile.load_image_file(filename)
      if self.imageData:
        self.imagePath = filename
      self.labelFile = None
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
    if self._config["keep_prev"]:
      prev_annotations = self.canvas.annotations
    self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image))
    flags = {k: False for k in self._config["flags"] or []}
    if self.labelFile:
      self.loadLabels(self.labelFile.annotations)
      if self.labelFile.flags is not None:
        flags.update(self.labelFile.flags)
    self.loadFlags(flags)
    if self._config["keep_prev"] and self.noAnnotations():
      self.loadAnnotations(prev_annotations, replace=False)
      self.setDirty()
    else:
      self.setClean()
    self.canvas.setEnabled(True)
    # set zoom values
    is_initial_load = not self.zoom_values
    if self.filename in self.zoom_values:
      self.zoomMode = self.zoom_values[self.filename][0]
      self.setZoom(self.zoom_values[self.filename][1])
    elif is_initial_load or not self._config["keep_prev_scale"]:
      self.adjustScale(initial=True)
    # set scroll values
    for orientation in self.scroll_values:
      if self.filename in self.scroll_values[orientation]:
        self.setScroll(
          orientation, self.scroll_values[orientation][self.filename]
        )
    # set brightness constrast values
    dialog = BrightnessContrastDialog(
      utils.img_data_to_pil(self.imageData),
      self.onNewBrightnessContrast,
      parent=self,
    )
    brightness, contrast = self.brightnessContrast_values.get(
      self.filename, (None, None)
    )
    if self._config["keep_prev_brightness"] and self.recentFiles:
      brightness, _ = self.brightnessContrast_values.get(
        self.recentFiles[0], (None, None)
      )
    if self._config["keep_prev_contrast"] and self.recentFiles:
      _, contrast = self.brightnessContrast_values.get(
        self.recentFiles[0], (None, None)
      )
    if brightness is not None:
      dialog.slider_brightness.setValue(brightness)
    if contrast is not None:
      dialog.slider_contrast.setValue(contrast)
    self.brightnessContrast_values[self.filename] = (brightness, contrast)
    if brightness is not None or contrast is not None:
      dialog.onNewValue(None)
    self.paintCanvas()
    self.addRecentFile(self.filename)
    self.toggleActions(True)
    self.status(self.tr("Loaded %s") % osp.basename(str(filename)))
    return True

  def resizeEvent(self, event):
    if (
      self.canvas
      and not self.image.isNull()
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
    self._config["store_data"] = enabled
    self.actions.saveWithImageData.setChecked(enabled)

  def closeEvent(self, event):
    if not self.mayContinue():      event.ignore()
    self.settings.setValue(
      "filename", self.filename if self.filename else ""
    )
    self.settings.setValue("window/size", self.size())
    self.settings.setValue("window/position", self.pos())
    self.settings.setValue("window/state", self.saveState())
    self.settings.setValue("recentFiles", self.recentFiles)
    # ask the use for where to save the labels
    # self.settings.setValue('window/geometry', self.saveGeometry())

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
    keep_prev = self._config["keep_prev"]
    if Qt.KeyboardModifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
      self._config["keep_prev"] = True

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

    self._config["keep_prev"] = keep_prev

  def openNextImg(self, _value=False, load=True):
    keep_prev = self._config["keep_prev"]
    if Qt.KeyboardModifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
      self._config["keep_prev"] = True

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
    self.filename = filename

    if self.filename and load:
      self.loadFile(self.filename)

    self._config["keep_prev"] = keep_prev

  def openFile(self, _value=False):
    if not self.mayContinue():
      return
    path = osp.dirname(str(self.filename)) if self.filename else "."
    formats = [
      "*.{}".format(fmt.data().decode())
      for fmt in QtGui.QImageReader.supportedImageFormats()
    ]
    filters = self.tr("Image & Label files (%s)") % " ".join(
      formats + ["*%s" % LabelFile.suffix]
    )
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
      default_labelfile_name = osp.join(
        self.output_dir, basename + LabelFile.suffix
      )
    else:
      default_labelfile_name = osp.join(
        self.currentPath(), basename + LabelFile.suffix
      )
    filename = dlg.getSaveFileName(
      self,
      self.tr("Choose File"),
      default_labelfile_name,
      self.tr("Label files (*%s)") % LabelFile.suffix,
    )
    if isinstance(filename, tuple):
      filename, _ = filename
    return filename

  def _saveFile(self, filename):
    if filename and self.saveLabels(filename):
      self.addRecentFile(filename)
      self.setClean()

  def closeFile(self, _value=False):
    if not self.mayContinue():
      return
    self.resetState()
    self.setClean()
    self.toggleActions(False)
    self.canvas.setEnabled(False)
    self.actions.saveAs.setEnabled(False)

  def getLabelFile(self):
    if self.filename.lower().endswith(".json"):
      label_file = self.filename
    else:
      label_file = osp.splitext(self.filename)[0] + ".json"

    return label_file

  def deleteFile(self):
    mb = QtWidgets.QMessageBox
    msg = self.tr(
      "You are about to permanently delete this label file, "
      "proceed anyway?"
    )
    answer = mb.warning(self, self.tr("Attention"), msg, mb.Yes | mb.No)
    if not answer == mb.Yes:      return

    label_file = self.getLabelFile()
    if osp.exists(label_file):
      os.remove(label_file)
      logger.info("Label file is removed: {}".format(label_file))

      item = self.fileListWidget.currentItem()
      item.setCheckState(Qt.Unchecked)

      self.resetState()

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

  def onChangeLanguage(self, _value=False):
    languages = [self.tr(language) for language in self.support_language]
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

    QtWidgets.QApplication.exit(MainWindow.RESTART_CODE + languages.index(language))

  def onExportPixel(self):
    caption = self.tr("%s - Choose File") % __appname__
    filters = self.tr("Label files (*%s)") % LabelFile.suffix

  def onExportVOC(self):
    if not self.output_dir:   self.onChangeOutputDir()

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
    annotations = []
    for imagename in imageList:
      label_file = osp.splitext(imagename)[0] + ".json"
      labelFile = None
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

      annotations.extend(labelFile.annotations)
    
    if all(annotation["shape_type"]=="rectangle" for annotation in annotations):
      AnnotationType = "bbox_detection"
    elif any(annotation["shape_type"]=="polygon" for annotation in annotations):
      AnnotationType = "segmenation"

    print("Creating dataset VOC:", self.output_dir)

    class_names = []
    for annotation in annotations:
      if not annotation["label"] in class_names:
        class_names.append(annotation["label"])
    class_names = tuple(class_names)

    if osp.isdir(osp.join(self.output_dir, "VOC")):
      shutil.rmtree(osp.join(self.output_dir, "VOC"))

    if AnnotationType == "bbox_detection":
      os.makedirs(osp.join(self.output_dir, "VOC"))
      os.makedirs(osp.join(self.output_dir, "VOC", "JPEGImages"))
      os.makedirs(osp.join(self.output_dir, "VOC", "Annotations"))
      os.makedirs(osp.join(self.output_dir, "VOC", "AnnotationsVisualization"))

      for imagename in imageList:
        base = osp.splitext(osp.basename(imagename))[0]
        out_img_file = osp.join(self.output_dir, "VOC", "JPEGImages", base + ".jpg")
        out_xml_file = osp.join(self.output_dir, "VOC", "Annotations", base + ".xml")
        out_viz_file = osp.join(self.output_dir, "VOC", "AnnotationsVisualization", base + ".jpg")

        label_file = osp.splitext(imagename)[0] + ".json"
        labelFile = LabelFile(label_file)

        img = utils.img_data_to_arr(labelFile.imageData)
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
        for annotation in labelFile.annotations:
          class_name = annotation["label"]
          class_id = class_names.index(class_name)

          (xmin, ymin), (xmax, ymax) = annotation["points"]
          # swap if min is larger than max.
          xmin, xmax = sorted([xmin, xmax])
          ymin, ymax = sorted([ymin, ymax])

          bboxes.append([ymin, xmin, ymax, xmax])
          labels.append(class_id)

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

        captions = [class_names[label] for label in labels]
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


  def onExportCOCO(self):
    caption = self.tr("%s - Choose File") % __appname__
    filters = self.tr("Label files (*%s)") % LabelFile.suffix

  def onImportPixel(self):
    caption = self.tr("%s - Choose File") % __appname__
    filters = self.tr("Label files (*%s)") % LabelFile.suffix

  def onImportVOC(self):
    caption = self.tr("%s - Choose File") % __appname__
    filters = self.tr("Label files (*%s)") % LabelFile.suffix

  def onImportCOCO(self):
    caption = self.tr("%s - Choose File") % __appname__
    filters = self.tr("Label files (*%s)") % LabelFile.suffix

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

    label_file = self.getLabelFile()
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
    self._config["keep_prev"] = not self._config["keep_prev"]

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
    if not self.mayContinue():
      return

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
    lst = []
    for i in range(self.fileListWidget.count()):
      item = self.fileListWidget.item(i)
      lst.append(item.text())
    return lst

  def importDroppedImageFiles(self, imageFiles):
    extensions = [
      ".%s" % fmt.data().decode().lower()
      for fmt in QtGui.QImageReader.supportedImageFormats()
    ]

    self.filename = None
    for file in imageFiles:
      if file in self.imageList or not file.lower().endswith(
        tuple(extensions)
      ):
        continue
      label_file = osp.splitext(file)[0] + ".json"
      if self.output_dir:
        label_file_without_path = osp.basename(label_file)
        label_file = osp.join(self.output_dir, label_file_without_path)
      item = QtWidgets.QListWidgetItem(file)
      item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
      if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(
        label_file
      ):
        item.setCheckState(Qt.Checked)
      else:
        item.setCheckState(Qt.Unchecked)
      self.fileListWidget.addItem(item)

    if len(self.imageList) > 1:
      self.actions.openNextImg.setEnabled(True)
      self.actions.openPrevImg.setEnabled(True)

    self.openNextImg()

  def importDirImages(self, dirpath, pattern=None, load=True):
    self.actions.openNextImg.setEnabled(True)
    self.actions.openPrevImg.setEnabled(True)

    if not self.mayContinue() or not dirpath:
      return

    self.lastOpenDir = dirpath
    self.filename = None
    self.fileListWidget.clear()
    for filename in self.scanAllImages(dirpath):
      if pattern and pattern not in filename:
        continue
      label_file = osp.splitext(filename)[0] + ".json"
      if self.output_dir:
        label_file_without_path = osp.basename(label_file)
        label_file = osp.join(self.output_dir, label_file_without_path)
      item = QtWidgets.QListWidgetItem(filename)
      item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
      if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(
        label_file
      ):
        item.setCheckState(Qt.Checked)
      else:
        item.setCheckState(Qt.Unchecked)
      self.fileListWidget.addItem(item)
    self.openNextImg(load=load)

  def scanAllImages(self, folderPath):
    extensions = [
      ".%s" % fmt.data().decode().lower()
      for fmt in QtGui.QImageReader.supportedImageFormats()
    ]

    images = []
    for root, dirs, files in os.walk(folderPath):
      for file in files:
        if file.lower().endswith(tuple(extensions)):
          relativePath = osp.join(root, file)
          images.append(relativePath)
      break; # not search subdirectory
    images.sort(key=lambda x: x.lower())
    return images
