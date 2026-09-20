import QtQuick
import Kfps.Theme 1.0
import "../components" as C

C.KfpsComboBox {
    dense: true
    crispText: true
    font.pixelSize: Math.round(Theme.px(13))
    implicitHeight: Math.round(Theme.px(36))
}
