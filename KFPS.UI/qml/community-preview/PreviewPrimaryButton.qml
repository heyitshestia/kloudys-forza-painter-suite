import QtQuick
import Kfps.Theme 1.0
import "../components" as C

C.PrimaryButton {
    dense: true
    crispText: true
    implicitHeight: Math.round(Theme.px(36))
    textPixelSize: Math.round(Theme.px(13))
}
