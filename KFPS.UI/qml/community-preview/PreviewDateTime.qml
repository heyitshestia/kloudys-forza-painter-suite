import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Kfps.Theme 1.0
import "../components" as C

RowLayout {
    id: root
    property string isoValue: makeIso()
    spacing: 5
    function setIso(value) {
        var date = new Date(value)
        day.text = Qt.formatDate(date, "yyyy-MM-dd")
        hours.text = String(date.getHours()).padStart(2, "0")
        minutes.text = String(date.getMinutes()).padStart(2, "0")
    }
    function makeIso() {
        if (!hours.acceptableInput || !minutes.acceptableInput) return ""
        var input = day.text + "T" + String(Number(hours.text)).padStart(2, "0") + ":" + String(Number(minutes.text)).padStart(2, "0")
        var date = new Date(input)
        if (isNaN(date.getTime()) || Qt.formatDateTime(date, "yyyy-MM-ddTHH:mm") !== input)
            return ""
        return date.toISOString()
    }
    C.KfpsTextField { font.pixelSize: Math.round(Theme.px(14)); renderType: TextInput.CurveRendering; id: day; Layout.fillWidth: true; Layout.minimumWidth: 105; placeholderText: "YYYY-MM-DD"; inputMask: "0000-00-00"; Accessible.name: preview.language === "ko" ? "날짜" : "Date" }
    C.KfpsTextField { font.pixelSize: Math.round(Theme.px(14)); renderType: TextInput.CurveRendering; id: hours; validator: IntValidator { bottom: 0; top: 23 } maximumLength: 2; placeholderText: "HH"; Layout.preferredWidth: 50; Layout.minimumWidth: 44; horizontalAlignment: TextInput.AlignHCenter; Accessible.name: preview.language === "ko" ? "시" : "Hour" }
    PreviewText { text: ":" }
    C.KfpsTextField { font.pixelSize: Math.round(Theme.px(14)); renderType: TextInput.CurveRendering; id: minutes; validator: IntValidator { bottom: 0; top: 59 } maximumLength: 2; placeholderText: "MM"; Layout.preferredWidth: 50; Layout.minimumWidth: 44; horizontalAlignment: TextInput.AlignHCenter; Accessible.name: preview.language === "ko" ? "분" : "Minute" }
}
