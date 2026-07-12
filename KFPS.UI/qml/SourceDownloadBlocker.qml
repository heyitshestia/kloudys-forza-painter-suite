import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7

ApplicationWindow {
    id: window

    visible: true
    width: 1360
    height: 820
    minimumWidth: 980
    minimumHeight: 620
    color: "#16070c"
    title: "KFPS - Wrong Download"

    property bool blinkOn: true
    readonly property string releaseUrl: sourceDownloadUrl && sourceDownloadUrl.length > 0
                                         ? sourceDownloadUrl
                                         : "https://github.com/heyitshestia/kloudys-forza-painter-suite/releases/latest"

    component GuardButton: Button {
        id: control

        property bool primary: false

        implicitWidth: Math.max(primary ? 190 : 112, buttonLabel.implicitWidth + 30)
        implicitHeight: 42
        padding: 0
        hoverEnabled: true
        font.family: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
        font.pixelSize: 14
        font.bold: primary

        contentItem: Text {
            id: buttonLabel
            text: control.text
            color: "#ffffff"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font: control.font
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: 6
            color: control.primary
                   ? (control.down ? "#8f111d" : (control.hovered ? "#d51f32" : "#b91224"))
                   : (control.down ? "#2a0b12" : (control.hovered ? "#44131d" : "#2f1018"))
            border.width: 1
            border.color: control.primary ? "#ff707d" : "#6d1e2a"
        }
    }

    Timer {
        interval: 460
        repeat: true
        running: !screenshotMode
        onTriggered: window.blinkOn = !window.blinkOn
    }

    Rectangle {
        anchors.fill: parent
        color: "#16070c"
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: "#5a1720"
    }

    Rectangle {
        id: warningBand
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 188
        color: window.blinkOn || screenshotMode ? "#350008" : "#170205"
        border.width: 2
        border.color: "#ff2332"

        Behavior on color {
            enabled: !screenshotMode
            ColorAnimation { duration: 120 }
        }

        Text {
            anchors.centerIn: parent
            width: parent.width - 48
            text: "WRONG DOWNLOAD"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: window.blinkOn || screenshotMode ? "#ff2332" : "#ff8c96"
            font.family: Qt.platform.os === "windows" ? "Segoe UI Black" : "Inter"
            font.pixelSize: 86
            font.bold: true
            fontSizeMode: Text.Fit
            minimumPixelSize: 48
            wrapMode: Text.NoWrap

            Behavior on color {
                enabled: !screenshotMode
                ColorAnimation { duration: 120 }
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: warningBand.bottom
        height: 5
        color: "#ff2332"
    }

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: warningBand.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 44
        spacing: 26

        RowLayout {
            Layout.fillWidth: true
            spacing: 22

            Image {
                Layout.preferredWidth: 86
                Layout.preferredHeight: 86
                source: assetRoot + "/kfps-logo.png"
                fillMode: Image.PreserveAspectFit
                visible: status === Image.Ready
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: sourceDownloadReason && sourceDownloadReason.length > 0
                          ? sourceDownloadReason
                          : "GitHub main/source archive detected"
                    color: "#ffffff"
                    font.family: Qt.platform.os === "windows" ? "Segoe UI Variable Display" : "Inter"
                    font.pixelSize: 28
                    font.bold: true
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: "This folder is locked so KFPS cannot be used from a GitHub main/source download."
                    color: "#ffd6dc"
                    font.family: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
                    font.pixelSize: 17
                    wrapMode: Text.WordWrap
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: detailsText.implicitHeight + 42
            radius: 8
            color: "#230b11"
            border.width: 1
            border.color: "#77202c"

            Text {
                id: detailsText
                anchors.fill: parent
                anchors.margins: 20
                text: sourceDownloadDetails && sourceDownloadDetails.length > 0
                      ? sourceDownloadDetails
                      : "GitHub source downloads are for code, not for running KFPS.\nThey do not include the bundled Python runtime, Python dependencies, or the supported release folder layout.\nDownload the latest release instead and choose the bundled zip with Python included."
                color: "#f6e8ec"
                font.family: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
                font.pixelSize: 16
                lineHeight: 1.18
                wrapMode: Text.WordWrap
                verticalAlignment: Text.AlignVCenter
            }
        }

        Text {
            Layout.fillWidth: true
            text: "Download the latest release with bundled Python:"
            color: "#ffb4bd"
            font.family: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
            font.pixelSize: 16
            font.bold: true
        }

        TextField {
            id: releaseField
            Layout.fillWidth: true
            text: window.releaseUrl
            readOnly: true
            selectByMouse: true
            color: "#ffffff"
            selectedTextColor: "#22070d"
            selectionColor: "#ff9ca6"
            font.family: Qt.platform.os === "windows" ? "Cascadia Mono" : "monospace"
            font.pixelSize: 15
            leftPadding: 14
            rightPadding: 14
            background: Rectangle {
                radius: 6
                color: "#0f0508"
                border.width: 1
                border.color: releaseField.activeFocus ? "#ff707d" : "#6d1a25"
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            GuardButton {
                text: "Open Latest Release"
                primary: true
                onClicked: Qt.openUrlExternally(window.releaseUrl)
            }

            GuardButton {
                text: "Select Link"
                onClicked: {
                    releaseField.forceActiveFocus()
                    releaseField.selectAll()
                }
            }

            Item { Layout.fillWidth: true }

            GuardButton {
                text: "Close"
                onClicked: Qt.quit()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: bypassText.implicitHeight + 30
            radius: 8
            color: "#120609"
            border.width: 1
            border.color: "#4b1520"

            Text {
                id: bypassText
                anchors.fill: parent
                anchors.margins: 14
                text: sourceDownloadOverrideHint
                color: "#bfa8ae"
                font.family: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
