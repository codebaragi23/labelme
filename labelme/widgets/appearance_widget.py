from qtpy.QtCore import Qt
from qtpy.QtCore import Slot
from qtpy import QtGui
from qtpy import QtWidgets

from .. import utils


class AppearanceWidget(QtWidgets.QWidget):
  def __init__(self, callback=None):
    super(AppearanceWidget, self).__init__()
    self.slider_brightness = self._create_slider()
    self.slider_contrast = self._create_slider()

    resetBtn = QtWidgets.QPushButton(self.tr("Reset"))
    resetBtn.clicked.connect(self.onReset)

    if callback:
      PixelmapCkb = QtWidgets.QCheckBox(self.tr("Show pixelmap"))
      PixelmapCkb.stateChanged.connect(lambda:self.onChangeShowPixelmal(PixelmapCkb))

    formLayout = QtWidgets.QFormLayout()
    formLayout.addRow(self.tr("Brightness"), self.slider_brightness)
    formLayout.addRow(self.tr("Contrast"), self.slider_contrast)
    if callback:
      formLayout.addRow(PixelmapCkb)
    formLayout.addRow(resetBtn)
    self.setLayout(formLayout)
    
    self.callback = callback

  def setAnnotations(self, annotations):
    #self.canvas.annotations
    self.annotations = annotations

  @Slot(int)
  def onNewValue(self, value):
    brightness = self.slider_brightness.value() / 50.0
    contrast = self.slider_contrast.value() / 50.0
    self.callback(brightness, contrast)

  @Slot()
  def onReset(self):
    self.slider_brightness.setValue(50)
    self.slider_contrast.setValue(50)

  @Slot("QCheckBox")
  def onChangeShowPixelmal(self, ckb):
    if ckb.isChecked():
      for annotation in self.annotations:
        annotation.show_pixelmap = True
      self.brightness = self.slider_brightness.value()
      self.slider_brightness.setValue(0)
    else:
      for annotation in self.annotations:
        annotation.show_pixelmap = False
      self.slider_brightness.setValue(self.brightness)

  def _create_slider(self):
    slider = QtWidgets.QSlider(Qt.Horizontal)
    slider.setRange(0, 150)
    slider.setValue(50)
    slider.valueChanged.connect(self.onNewValue)
    return slider
