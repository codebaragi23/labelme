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
  def onSliderValueChanged(self, value):
    self.brightness = self.slider_brightness.value() / 50.0
    self.contrast = self.slider_contrast.value() / 50.0
    self.callback(brightness=self.brightness, contrast=self.contrast)

  @Slot()
  def onReset(self):
    self.slider_brightness.setValue(50)
    self.slider_contrast.setValue(50)

  @Slot("QCheckBox")
  def onChangeShowPixelmal(self, ckb):
    if ckb.isChecked():
      self.brightness = self.slider_brightness.value() / 50.0
      self.contrast = self.slider_contrast.value() / 50.0
      with utils.slot_disconnected(self.slider_brightness.valueChanged, self.onSliderValueChanged):
        self.slider_brightness.setValue(0)
      self.callback(show_pixelmap=True)
    else:
      with utils.slot_disconnected(self.slider_brightness.valueChanged, self.onSliderValueChanged):
        self.slider_brightness.setValue(self.brightness * 50.0)
      with utils.slot_disconnected(self.slider_contrast.valueChanged, self.onSliderValueChanged):
        self.slider_contrast.setValue(self.contrast * 50.0)
      self.callback(brightness=self.brightness, contrast=self.contrast, show_pixelmap=False)

  def _create_slider(self):
    slider = QtWidgets.QSlider(Qt.Horizontal)
    slider.setRange(0, 150)
    slider.setValue(50)
    slider.valueChanged.connect(self.onSliderValueChanged)
    return slider
