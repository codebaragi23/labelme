from qtpy import QtCore, QtWidgets, QT_VERSION
import json

class QJsonTreeWidget(QtWidgets.QTreeWidget):
  def __init__(self):
    super().__init__()
    self.setHeaderItem(QtWidgets.QTreeWidgetItem([self.tr("Key"), self.tr("Value")]))

  def loadJson(self, filename):
    self.clear()
    
    document = json.load(open(filename))

    assert isinstance(document, (dict, list, tuple)), (
      "`document` must be of dict, list or tuple, "
      "not %s" % type(document)
    )

    root = self.load(document)
    self.addTopLevelItems(root.takeChildren())
    self.expandAll()

    header = self.header()
    header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    header.setStretchLastSection(True)
    #header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

  def load(self, value, parent=None, sort=False):
    item = QtWidgets.QTreeWidgetItem(parent)

    if isinstance(value, dict):
      items = (
        sorted(value.items())
        if sort else value.items()
      )

      for key, val in items:
        child = self.load(val, item)
        child.setText(0, str(key))

    elif isinstance(value, list):
      for index, val in enumerate(value):
        child = self.load(val, item)
        if child.text(1) is "":
          child.setText(0, f"job-{index}")

    else:
      item.setText(1, str(value))

    return item

      