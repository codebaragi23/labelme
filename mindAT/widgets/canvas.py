from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets

from mindAT import QT5
from mindAT.annotation import Annotation
from mindAT.widgets import AppearanceWidget

import mindAT.utils
import mindAT.eval

import cv2
import numpy as np

# TODO(unknown):
# - [maybe] Find optimal epsilon value.
DEFAULT_TEXT_COLOR = QtGui.QColor(0, 0, 0)
DEFAULT_TEXT_BACKGROUND_COLOR = QtGui.QColor(128, 128, 128, 156)

CURSOR_DEFAULT = QtCore.Qt.ArrowCursor
CURSOR_POINT = QtCore.Qt.PointingHandCursor
CURSOR_DRAW = QtCore.Qt.CrossCursor
CURSOR_MOVE = QtCore.Qt.ClosedHandCursor
CURSOR_GRAB = QtCore.Qt.OpenHandCursor


class Canvas(QtWidgets.QWidget):
  zoomRequest = QtCore.Signal(int, QtCore.QPoint)
  scrollRequest = QtCore.Signal(int, int)
  newAnnotation = QtCore.Signal()
  selectionChanged = QtCore.Signal(list)
  annotationMoved = QtCore.Signal()
  drawingPolygon = QtCore.Signal(bool)
  edgeSelected = QtCore.Signal(bool, object)
  vertexSelected = QtCore.Signal(bool)

  CREATE, EDIT, MOVE = 0, 1, 2

  # polygon, rectangle, line, or point
  _createMode = "polygon"
  _fill_drawing = False

  activeAction = None

  def __init__(self, *args, **kwargs):
    self.epsilon = kwargs.pop("epsilon", 10.0)
    self.double_click = kwargs.pop("double_click", "close")
    if self.double_click not in [None, "close"]:
      raise ValueError(
        "Unexpected value for double_click event: {}".format(
          self.double_click
        )
      )
    super(Canvas, self).__init__(*args, **kwargs)
    # Initialise local state.
    self.mode = self.EDIT
    self.show_pixelmap = False
    self.show_groundtruth = True
    self.annotations = []
    self.groundtruth = []
    self.eval_method = AppearanceWidget.EVAL_PIXEL_ACCURACY
    self.annotationsBackups = []
    self.current = None
    self.selectedAnnotations = []  # save the selected annotations here
    self.selectedAnnotationsCopy = []
    # self.line represents:
    #   - createMode == 'polygon': edge from last point to current
    #   - createMode == 'rectangle': diagonal line of the rectangle
    #   - createMode == 'line': the line
    #   - createMode == 'point': the point
    self.line = Annotation()
    self.prevPoint = QtCore.QPoint()
    self.prevMovePoint = QtCore.QPoint()
    self.offsets = QtCore.QPoint(), QtCore.QPoint()
    self.scale = 1.0
    self.pixmap = QtGui.QPixmap()
    self.visible = {}
    self._hideBackround = False
    self.hideBackround = False
    self.hAnnotation = None
    self.prevhAnnotation = None
    self.hVertex = None
    self.prevhVertex = None
    self.hEdge = None
    self.prevhEdge = None
    self.movingAnnotation = False
    self._painter = QtGui.QPainter()
    self._cursor = CURSOR_DEFAULT
    # Menus:
    # 0: right-click without selection and dragging of annotations
    # 1: right-click with selection and dragging of annotations
    self.menus = (QtWidgets.QMenu(), QtWidgets.QMenu())
    # Set widget options.
    self.setMouseTracking(True)
    self.setFocusPolicy(QtCore.Qt.WheelFocus)

  def setEvalMethod(self, method):
    self.eval_method = method
    self.repaint()

  @property
  def createMode(self):
    return self._createMode

  @createMode.setter
  def createMode(self, value):
    if value not in [
      "polygon",
      "rectangle",
      "circle",
      "line",
      "point",
      "linestrip",
    ]:
      raise ValueError("Unsupported createMode: %s" % value)
    self._createMode = value

  def storeAnnotations(self):
    annotationsBackup = []
    for annotation in self.annotations:
      annotationsBackup.append(annotation.copy())
    if len(self.annotationsBackups) >= 10:
      self.annotationsBackups = self.annotationsBackups[-9:]
    self.annotationsBackups.append(annotationsBackup)

  @property
  def isAnnotationRestorable(self):
    if len(self.annotationsBackups) < 2:
      return False
    return True

  def restoreAnnotation(self):
    if not self.isAnnotationRestorable:
      return
    self.annotationsBackups.pop()  # latest
    annotationsBackup = self.annotationsBackups.pop()
    self.annotations = annotationsBackup
    self.selectedAnnotations = []
    for annotation in self.annotations:
      annotation.selected = False
    self.repaint()

  def enterEvent(self, event):
    self.overrideCursor(self._cursor)

  def leaveEvent(self, event):
    self.unHighlight()
    self.restoreCursor()

  def focusOutEvent(self, event):
    self.restoreCursor()

  def isVisible(self, annotation):
    return self.visible.get(annotation, True)

  def drawing(self):
    return self.mode == self.CREATE

  def editing(self):
    return self.mode == self.EDIT

  def moving(self):
    return self.mode == self.MOVE

  def setEditing(self, value=True):
    self.mode = self.EDIT if value else self.CREATE
    self.cancelDrawing()
    if not value:  # Create
      self.unHighlight()
      self.deSelectAnnotation()
  
  def setMoving(self, value=True):
    self.mode = self.MOVE if value else self.EDIT
    self.cancelDrawing()

  def unHighlight(self):
    if self.hAnnotation:
      self.hAnnotation.highlightClear()
      self.update()
    self.prevhAnnotation = self.hAnnotation
    self.prevhVertex = self.hVertex
    self.prevhEdge = self.hEdge
    self.hAnnotation = self.hVertex = self.hEdge = None

  def selectedVertex(self):
    return self.hVertex is not None

  def mouseMoveEvent(self, event):
    """Update line with last point and current coordinates."""
    try:
      if QT5:
        pos = self.transformPos(event.localPos())
      else:
        pos = self.transformPos(event.posF())
    except AttributeError:
      return

    self.prevMovePoint = pos
    self.restoreCursor()

    # Polygon drawing.
    if self.drawing():
      self.line.shape_type = self.createMode

      self.overrideCursor(CURSOR_DRAW)
      if not self.current:
        return

      if self.outOfPixmap(pos):
        # Don't allow the user to draw outside the pixmap.
        # Project the point to the pixmap's edges.
        pos = self.intersectionPoint(self.current[-1], pos)
      elif (
        len(self.current) > 1
        and self.createMode == "polygon"
        and self.closeEnough(pos, self.current[0])
      ):
        # Attract line to starting point and
        # colorise to alert the user.
        pos = self.current[0]
        self.overrideCursor(CURSOR_POINT)
        self.current.highlightVertex(0, Annotation.NEAR_VERTEX)
      if self.createMode in ["polygon", "linestrip"]:
        self.line[0] = self.current[-1]
        self.line[1] = pos
      elif self.createMode == "rectangle":
        self.line.points = [self.current[0], pos]
        self.line.close()
      elif self.createMode == "circle":
        self.line.points = [self.current[0], pos]
        self.line.shape_type = "circle"
      elif self.createMode == "line":
        self.line.points = [self.current[0], pos]
        self.line.close()
      elif self.createMode == "point":
        self.line.points = [self.current[0]]
        self.line.close()
      self.repaint()
      self.current.highlightClear()
      return

    # Polygon copy moving.
    if QtCore.Qt.RightButton & event.buttons():
      if self.selectedAnnotationsCopy and self.prevPoint:
        self.overrideCursor(CURSOR_MOVE)
        self.boundedMoveAnnotations(self.selectedAnnotationsCopy, pos)
        self.repaint()
      elif self.selectedAnnotations:
        self.selectedAnnotationsCopy = [
          s.copy() for s in self.selectedAnnotations
        ]
        self.repaint()
      return

    # Polygon/Vertex moving.
    if QtCore.Qt.LeftButton & event.buttons():
      if self.selectedVertex():
        self.boundedMoveVertex(pos)
        self.repaint()
        self.movingAnnotation = True
      elif self.moving() and self.selectedAnnotations and self.prevPoint:
        self.overrideCursor(CURSOR_MOVE)
        self.boundedMoveAnnotations(self.selectedAnnotations, pos)
        self.repaint()
        self.movingAnnotation = True
      return

    # Just hovering over the canvas, 2 possibilities:
    # - Highlight annotations
    # - Highlight vertex
    # Update annotation/vertex fill and tooltip value accordingly.
    self.setToolTip(self.tr("Image"))
    for annotation in reversed([s for s in self.annotations if self.isVisible(s)]):
      # Look for a nearby vertex to highlight. If that fails,
      # check if we happen to be inside a annotation.
      index = annotation.nearestVertex(pos, self.epsilon / self.scale)
      index_edge = annotation.nearestEdge(pos, self.epsilon / self.scale)
      if index is not None:
        if self.selectedVertex():
          self.hAnnotation.highlightClear()
        self.prevhVertex = self.hVertex = index
        self.prevhAnnotation = self.hAnnotation = annotation
        self.prevhEdge = self.hEdge = index_edge
        annotation.highlightVertex(index, annotation.MOVE_VERTEX)
        self.overrideCursor(CURSOR_POINT)
        self.setToolTip(self.tr("Click & drag to move point"))
        self.setStatusTip(self.toolTip())
        self.update()
        break
      elif self.moving() and annotation.containsPoint(pos):
        if self.selectedVertex():
          self.hAnnotation.highlightClear()
        self.prevhVertex = self.hVertex
        self.hVertex = None
        self.prevhAnnotation = self.hAnnotation = annotation
        self.prevhEdge = self.hEdge = index_edge
        self.setToolTip(
          self.tr("Click & drag to move annotation '%s'") % annotation.label
        )
        self.setStatusTip(self.toolTip())
        self.overrideCursor(CURSOR_GRAB)
        self.update()
        break
    else:  # Nothing found, clear highlights, reset state.
      self.unHighlight()
    self.edgeSelected.emit(self.hEdge is not None, self.hAnnotation)
    self.vertexSelected.emit(self.hVertex is not None)

  def addPointToEdge(self):
    annotation = self.prevhAnnotation
    index = self.prevhEdge
    point = self.prevMovePoint
    if annotation is None or index is None or point is None:
      return
    annotation.insertPoint(index, point)
    annotation.highlightVertex(index, annotation.MOVE_VERTEX)
    self.hAnnotation = annotation
    self.hVertex = index
    self.hEdge = None
    self.movingAnnotation = True

  def removeSelectedPoint(self):
    annotation = self.prevhAnnotation
    point = self.prevMovePoint
    if annotation is None or point is None:
      return
    index = annotation.nearestVertex(point, self.epsilon)
    annotation.removePoint(index)
    # annotation.highlightVertex(index, annotation.MOVE_VERTEX)
    self.hAnnotation = annotation
    self.hVertex = None
    self.hEdge = None
    self.movingAnnotation = True  # Save changes

  def mousePressEvent(self, event):
    if QT5:
      pos = self.transformPos(event.localPos())
    else:
      pos = self.transformPos(event.posF())
    if event.button() == QtCore.Qt.LeftButton:
      if self.drawing():
        if self.current:
          # Add point to existing annotation.
          if self.createMode == "polygon":
            self.current.addPoint(self.line[1])
            self.line[0] = self.current[-1]
            if self.current.isClosed():
              self.finalise()
          elif self.createMode in ["rectangle", "circle", "line"]:
            assert len(self.current.points) == 1
            self.current.points = self.line.points
            self.finalise()
          elif self.createMode == "linestrip":
            self.current.addPoint(self.line[1])
            self.line[0] = self.current[-1]
            if int(event.modifiers()) == QtCore.Qt.ControlModifier:
              self.finalise()
        elif not self.outOfPixmap(pos):
          # Create new annotation.
          self.current = Annotation(shape_type=self.createMode)
          self.current.addPoint(pos)
          if self.createMode == "point":
            self.finalise()
          else:
            if self.createMode == "circle":
              self.current.shape_type = "circle"
            self.line.points = [pos, pos]
            self.setHiding()
            self.drawingPolygon.emit(True)
            self.update()
      else:
        group_mode = int(event.modifiers()) == QtCore.Qt.ControlModifier
        self.selectAnnotationPoint(pos, multiple_selection_mode=group_mode)
        self.prevPoint = pos
        self.repaint()
    elif event.button() == QtCore.Qt.RightButton and self.editing():
      group_mode = int(event.modifiers()) == QtCore.Qt.ControlModifier
      self.selectAnnotationPoint(pos, multiple_selection_mode=group_mode)
      self.prevPoint = pos
      self.repaint()

  def mouseReleaseEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
      menu = self.menus[len(self.selectedAnnotationsCopy) > 0]
      self.restoreCursor()
      if (
        not menu.exec_(self.mapToGlobal(event.pos()))
        and self.selectedAnnotationsCopy
      ):
        # Cancel the move by deleting the shadow copy.
        self.selectedAnnotationsCopy = []
        self.repaint()
    elif event.button() == QtCore.Qt.LeftButton and self.selectedAnnotations:
      self.overrideCursor(CURSOR_GRAB)
      if (
        self.editing()
        and int(event.modifiers()) == QtCore.Qt.ShiftModifier
      ):
        # Add point to line if: left-click + SHIFT on a line segment
        self.addPointToEdge()
    elif event.button() == QtCore.Qt.LeftButton and self.selectedVertex():
      if (
        self.editing()
        and int(event.modifiers()) == QtCore.Qt.ShiftModifier
      ):
        # Delete point if: left-click + SHIFT on a point
        self.removeSelectedPoint()

    if self.movingAnnotation and self.hAnnotation:
      index = self.annotations.index(self.hAnnotation)
      if (
        self.annotationsBackups[-1][index].points
        != self.annotations[index].points
      ):
        self.storeAnnotations()
        self.annotationMoved.emit()

      self.movingAnnotation = False

  def endMove(self, copy):
    assert self.selectedAnnotations and self.selectedAnnotationsCopy
    assert len(self.selectedAnnotationsCopy) == len(self.selectedAnnotations)
    if copy:
      for i, annotation in enumerate(self.selectedAnnotationsCopy):
        self.annotations.append(annotation)
        self.selectedAnnotations[i].selected = False
        self.selectedAnnotations[i] = annotation
    else:
      for i, annotation in enumerate(self.selectedAnnotationsCopy):
        self.selectedAnnotations[i].points = annotation.points
    self.selectedAnnotationsCopy = []
    self.repaint()
    self.storeAnnotations()
    return True

  def hideBackroundAnnotations(self, value):
    self.hideBackround = value
    if self.selectedAnnotations:
      # Only hide other annotations if there is a current selection.
      # Otherwise the user will not be able to select a annotation.
      self.setHiding(True)
      self.repaint()

  def setHiding(self, enable=True):
    self._hideBackround = self.hideBackround if enable else False

  def canCloseAnnotation(self):
    return self.drawing() and self.current and len(self.current) > 2

  def mouseDoubleClickEvent(self, event):
    # We need at least 4 points here, since the mousePress handler
    # adds an extra one before this handler is called.
    if (
      self.double_click == "close"
      and self.canCloseAnnotation()
      and len(self.current) > 3
    ):
      self.current.popPoint()
      self.finalise()

  def selectAnnotations(self, annotations):
    self.setHiding()
    self.selectionChanged.emit(annotations)
    self.update()

  def selectAnnotationPoint(self, point, multiple_selection_mode):
    """Select the first annotation created which contains this point."""
    if self.selectedVertex():  # A vertex is marked for selection.
      index, annotation = self.hVertex, self.hAnnotation
      annotation.highlightVertex(index, annotation.MOVE_VERTEX)
    else:
      for annotation in reversed(self.annotations):
        if self.isVisible(annotation) and annotation.containsPoint(point):
          self.calculateOffsets(annotation, point)
          self.setHiding()
          if multiple_selection_mode:
            if annotation not in self.selectedAnnotations:
              self.selectionChanged.emit(
                self.selectedAnnotations + [annotation]
              )
          else:
            self.selectionChanged.emit([annotation])
          return
    self.deSelectAnnotation()

  def calculateOffsets(self, annotation, point):
    rect = annotation.boundingRect()
    x1 = rect.x() - point.x()
    y1 = rect.y() - point.y()
    x2 = (rect.x() + rect.width() - 1) - point.x()
    y2 = (rect.y() + rect.height() - 1) - point.y()
    self.offsets = QtCore.QPoint(x1, y1), QtCore.QPoint(x2, y2)

  def boundedMoveVertex(self, pos):
    index, annotation = self.hVertex, self.hAnnotation
    point = annotation[index]
    if self.outOfPixmap(pos):
      pos = self.intersectionPoint(point, pos)
    annotation.moveVertexBy(index, pos - point)

  def boundedMoveAnnotations(self, annotations, pos):
    if self.outOfPixmap(pos):
      return False  # No need to move
    o1 = pos + self.offsets[0]
    if self.outOfPixmap(o1):
      pos -= QtCore.QPoint(min(0, o1.x()), min(0, o1.y()))
    o2 = pos + self.offsets[1]
    if self.outOfPixmap(o2):
      pos += QtCore.QPoint(
        min(0, self.pixmap.width() - o2.x()),
        min(0, self.pixmap.height() - o2.y()),
      )
    # XXX: The next line tracks the new position of the cursor
    # relative to the annotation, but also results in making it
    # a bit "shaky" when nearing the border and allows it to
    # go outside of the annotation's area for some reason.
    # self.calculateOffsets(self.selectedAnnotations, pos)
    dp = pos - self.prevPoint
    if dp:
      for annotation in annotations:
        annotation.moveBy(dp)
      self.prevPoint = pos
      return True
    return False

  def deSelectAnnotation(self):
    if self.selectedAnnotations:
      self.setHiding(False)
      self.selectionChanged.emit([])
      self.update()

  def deleteSelected(self):
    deleted_annotations = []
    if self.selectedAnnotations:
      for annotation in self.selectedAnnotations:
        self.annotations.remove(annotation)
        deleted_annotations.append(annotation)
      self.storeAnnotations()
      self.selectedAnnotations = []
      self.update()
    return deleted_annotations

  def copySelectedAnnotations(self):
    if self.selectedAnnotations:
      self.selectedAnnotationsCopy = [s.copy() for s in self.selectedAnnotations]
      self.boundedShiftAnnotations(self.selectedAnnotationsCopy)
      self.endMove(copy=True)
    return self.selectedAnnotations

  def boundedShiftAnnotations(self, annotations):
    # Try to move in one direction, and if it fails in another.
    # Give up if both fail.
    point = annotations[0][0]
    offset = QtCore.QPoint(2.0, 2.0)
    self.offsets = QtCore.QPoint(), QtCore.QPoint()
    self.prevPoint = point
    if not self.boundedMoveAnnotations(annotations, point - offset):
      self.boundedMoveAnnotations(annotations, point + offset)

  def paintEvent(self, event):
    if not self.pixmap:
      return super(Canvas, self).paintEvent(event)

    p = self._painter
    p.begin(self)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

    p.scale(self.scale, self.scale)
    p.translate(self.offsetToCenter())

    p.drawPixmap(0, 0, self.pixmap)
    Annotation.scale = self.scale
    if self.show_groundtruth and len(self.groundtruth)>0:
      for gt in self.groundtruth:
        gt.paint_pixelmap(p)

      eval = np.zeros((self.pixmap.height(), self.pixmap.width(), 3), np.uint8)
      for annotation in self.annotations:
        if annotation.label in ["__ignore__", "background"]: continue
        points = []
        if annotation.shape_type == "polygon":
          for pt in annotation.points: points.append([pt.x(), pt.y()])
        elif annotation.shape_type == "rectangle":
          pt1 = annotation.points[0]
          pt2 = annotation.points[1]
          points.append([pt1.x(), pt1.y()])
          points.append([pt2.x(), pt1.y()])
          points.append([pt2.x(), pt2.y()])
          points.append([pt1.x(), pt2.y()])
        else:
          raise TypeError(
            "Not support annotation shae_type {}".format(annotation.shape_type)
          )
        
        points = np.array(points, np.int32)
        cv2.fillPoly(eval, [points], annotation.fill_color.getRgb()[:3][::-1])
      eval = cv2.cvtColor(eval, cv2.COLOR_BGR2GRAY)
      #cv2.imwrite("map1.jpg", eval)

      gt = np.zeros((self.pixmap.height(), self.pixmap.width(), 3), np.uint8)
      for annotation in self.groundtruth:
        if annotation.label in ["__ignore__", "background"]: continue
        points = []
        for pt in annotation.points: points.append([pt.x(), pt.y()])
        
        points = np.array(points, np.int32)
        cv2.fillPoly(gt, [points], annotation.fill_color.getRgb()[:3][::-1])
      gt = cv2.cvtColor(gt, cv2.COLOR_BGR2GRAY)
      #cv2.imwrite("map2.jpg", gt)

      p.setFont(QtGui.QFont('Consolas', 6))
      p.setPen(QtGui.QColor(DEFAULT_TEXT_COLOR))

      eval_text = ""
      if self.eval_method == AppearanceWidget.EVAL_PIXEL_ACCURACY:
        eval_val = mindAT.eval.pixel_accuracy(eval, gt)
        eval_text = " Pixel accuracy: %d%%" % round(eval_val*100)
      elif self.eval_method == AppearanceWidget.EVAL_MEAN_ACCURACY:
        eval_val = mindAT.eval.mean_accuracy(eval, gt)
        eval_text = " Mean accuracy: %d%%" % round(eval_val*100)
      elif self.eval_method == AppearanceWidget.EVAL_MEAN_IOU:
        eval_val = mindAT.eval.mean_IoU(eval, gt)
        eval_text = " Mean IoU: %d%%" % round(eval_val*100)
      elif self.eval_method == AppearanceWidget.EVAL_FREQUENCY_WEIGHTED_IOU:
        eval_val = mindAT.eval.frequency_weighted_IoU(eval, gt)
        eval_text = " Frequency Weighted IoU: %d%%" % round(eval_val*100)

      fm = QtGui.QFontMetrics(p.font())
      width = fm.width(eval_text)
      textRect = QtCore.QRect(10, 10, width, 10)
      p.fillRect(textRect, QtGui.QColor(DEFAULT_TEXT_BACKGROUND_COLOR))
      p.drawText(textRect, QtCore.Qt.AlignVCenter, eval_text)
      
      
    for annotation in self.annotations:
      if (annotation.selected or not self._hideBackround) and self.isVisible(annotation):
        if self.show_pixelmap:
          annotation.paint_pixelmap(p)
        else:
          annotation.fill = annotation.selected or annotation == self.hAnnotation
          annotation.paint(p)
    if self.current:
      self.current.paint(p)
      self.line.paint(p)
    if self.selectedAnnotationsCopy:
      for s in self.selectedAnnotationsCopy:
        s.paint(p)

    if (
      self.createMode == "polygon"
      and self.current is not None
      and len(self.current.points) >= 2
    ):
      drawing_annotation = self.current.copy()
      drawing_annotation.addPoint(self.line[1])
      drawing_annotation.fill = True
      drawing_annotation.paint(p)
    p.end()

  def transformPos(self, point):
    """Convert from widget-logical coordinates to painter-logical ones."""
    return point / self.scale - self.offsetToCenter()

  def offsetToCenter(self):
    s = self.scale
    area = super(Canvas, self).size()
    w, h = self.pixmap.width() * s, self.pixmap.height() * s
    aw, ah = area.width(), area.height()
    x = (aw - w) / (2 * s) if aw > w else 0
    y = (ah - h) / (2 * s) if ah > h else 0
    return QtCore.QPoint(x, y)

  def outOfPixmap(self, p):
    w, h = self.pixmap.width(), self.pixmap.height()
    return not (0 <= p.x() <= w - 1 and 0 <= p.y() <= h - 1)

  def finalise(self):
    assert self.current
    self.current.close()
    self.annotations.append(self.current)
    self.storeAnnotations()
    self.current = None
    self.setHiding(False)
    self.newAnnotation.emit()
    self.update()

  def closeEnough(self, p1, p2):
    # d = distance(p1 - p2)
    # m = (p1-p2).manhattanLength()
    # print "d %.2f, m %d, %.2f" % (d, m, d - m)
    # divide by scale to allow more precision when zoomed in
    return mindAT.utils.distance(p1 - p2) < (self.epsilon / self.scale)

  def intersectionPoint(self, p1, p2):
    # Cycle through each image edge in clockwise fashion,
    # and find the one intersecting the current line segment.
    # http://paulbourke.net/geometry/lineline2d/
    size = self.pixmap.size()
    points = [
      (0, 0),
      (size.width() - 1, 0),
      (size.width() - 1, size.height() - 1),
      (0, size.height() - 1),
    ]
    # x1, y1 should be in the pixmap, x2, y2 should be out of the pixmap
    x1 = min(max(p1.x(), 0), size.width() - 1)
    y1 = min(max(p1.y(), 0), size.height() - 1)
    x2, y2 = p2.x(), p2.y()
    d, i, (x, y) = min(self.intersectingEdges((x1, y1), (x2, y2), points))
    x3, y3 = points[i]
    x4, y4 = points[(i + 1) % 4]
    if (x, y) == (x1, y1):
      # Handle cases where previous point is on one of the edges.
      if x3 == x4:
        return QtCore.QPoint(x3, min(max(0, y2), max(y3, y4)))
      else:  # y3 == y4
        return QtCore.QPoint(min(max(0, x2), max(x3, x4)), y3)
    return QtCore.QPoint(x, y)

  def intersectingEdges(self, point1, point2, points):
    """Find intersecting edges.

    For each edge formed by `points', yield the intersection
    with the line segment `(x1,y1) - (x2,y2)`, if it exists.
    Also return the distance of `(x2,y2)' to the middle of the
    edge along with its index, so that the one closest can be chosen.
    """
    (x1, y1) = point1
    (x2, y2) = point2
    for i in range(4):
      x3, y3 = points[i]
      x4, y4 = points[(i + 1) % 4]
      denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
      nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
      nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
      if denom == 0:
        # This covers two cases:
        #   nua == nub == 0: Coincident
        #   otherwise: Parallel
        continue
      ua, ub = nua / denom, nub / denom
      if 0 <= ua <= 1 and 0 <= ub <= 1:
        x = x1 + ua * (x2 - x1)
        y = y1 + ua * (y2 - y1)
        m = QtCore.QPoint((x3 + x4) / 2, (y3 + y4) / 2)
        d = mindAT.utils.distance(m - QtCore.QPoint(x2, y2))
        yield d, i, (x, y)

  # These two, along with a call to adjustSize are required for the
  # scroll area.
  def sizeHint(self):
    return self.minimumSizeHint()

  def minimumSizeHint(self):
    if self.pixmap:
      return self.scale * self.pixmap.size()
    return super(Canvas, self).minimumSizeHint()

  def wheelEvent(self, event):
    if QT5:
      mods = event.modifiers()
      delta = event.angleDelta()
      if QtCore.Qt.ControlModifier == int(mods):
        # with Ctrl/Command key
        # zoom
        self.zoomRequest.emit(delta.y(), event.pos())
      else:
        # scroll
        self.scrollRequest.emit(delta.x(), QtCore.Qt.Horizontal)
        self.scrollRequest.emit(delta.y(), QtCore.Qt.Vertical)
    else:
      if event.orientation() == QtCore.Qt.Vertical:
        mods = event.modifiers()
        if QtCore.Qt.ControlModifier == int(mods):
          # with Ctrl/Command key
          self.zoomRequest.emit(event.delta(), event.pos())
        else:
          self.scrollRequest.emit(
            event.delta(),
            QtCore.Qt.Horizontal
            if (QtCore.Qt.ShiftModifier == int(mods))
            else QtCore.Qt.Vertical,
          )
      else:
        self.scrollRequest.emit(event.delta(), QtCore.Qt.Horizontal)
    event.accept()

  def cancelDrawing(self):
    self.current = None
    self.drawingPolygon.emit(False)
    self.update()

  def cancelAction(self):
    if self.activeAction and self.activeAction.isChecked():
      self.activeAction.setChecked(False);
      self.setEditing(True)
      self.restoreCursor()

  def keyPressEvent(self, event):
    key = event.key()
    if key == QtCore.Qt.Key_Escape:
      if self.current:
        self.cancelDrawing()
      else:
        self.cancelAction();
    elif key == QtCore.Qt.Key_Return and self.canCloseAnnotation():
      self.finalise()

  def setLastLabel(self, text, flags):
    assert text
    self.annotations[-1].label = text
    self.annotations[-1].flags = flags
    self.annotationsBackups.pop()
    self.storeAnnotations()
    return self.annotations[-1]

  def undoLastLine(self):
    assert self.annotations
    self.current = self.annotations.pop()
    self.current.setOpen()
    if self.createMode in ["polygon", "linestrip"]:
      self.line.points = [self.current[-1], self.current[0]]
    elif self.createMode in ["rectangle", "line", "circle"]:
      self.current.points = self.current.points[0:1]
    elif self.createMode == "point":
      self.current = None
    self.drawingPolygon.emit(True)

  def undoLastPoint(self):
    if not self.current or self.current.isClosed():
      return
    self.current.popPoint()
    if len(self.current) > 0:
      self.line[0] = self.current[-1]
    else:
      self.current = None
      self.drawingPolygon.emit(False)
    self.repaint()

  def loadPixmap(self, pixmap):
    self.pixmap = pixmap
    self.repaint()

  def loadAnnotations(self, annotations, replace=True):
    if replace:
      self.annotations = list(annotations)
    else:
      self.annotations.extend(annotations)
    self.storeAnnotations()
    self.current = None
    self.hAnnotation = None
    self.hVertex = None
    self.hEdge = None
    self.repaint()

  def setAnnotationVisible(self, annotation, value):
    self.visible[annotation] = value
    self.repaint()

  def overrideCursor(self, cursor):
    self.restoreCursor()
    self._cursor = cursor
    QtWidgets.QApplication.setOverrideCursor(cursor)

  def restoreCursor(self):
    QtWidgets.QApplication.restoreOverrideCursor()

  def resetState(self):
    self.restoreCursor()
    self.pixmap = None
    self.annotations = []
    self.annotationsBackups = []
    self.update()
    self.groundtruth = []
