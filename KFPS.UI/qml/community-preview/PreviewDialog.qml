import QtQuick
import QtQuick.Controls
import Kfps.Theme 1.0
import "../components" as C

Dialog {
    id: dialog
    padding: Theme.px(14)
    background: C.KfpsPopupSurface { cornerRadius: Theme.px(6) }
    header: PreviewText {
        text: dialog.title
        padding: Theme.px(14)
        textSize: Theme.px(18)
        textWeight: Font.DemiBold
    }
    footer: DialogButtonBox {
        visible: dialog.standardButtons !== Dialog.NoButton
        standardButtons: dialog.standardButtons
        padding: Theme.px(12)
        background: Item {}
        delegate: C.GhostButton {
            dense: true
            crispText: true
            textPixelSize: Math.round(Theme.px(12))
            implicitHeight: Math.round(Theme.px(36))
        }
    }
}
