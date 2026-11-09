import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0

Item {
    id: root
    required property var service
    property bool launchBusy: false
    signal buildRequested()
    readonly property var details: service.details
    readonly property bool narrow: Theme.logical(width) < 760
    property bool showParts: false
    readonly property var accountChoices: [{id: "", label: "Choose an account", available: false}].concat(
        service.accountOptions.map(account => ({id: account.id,
            label: account.label + (account.available ? "" : " (unavailable)"), available: account.available})))
    readonly property int selectedAccountIndex: Math.max(0, accountChoices.findIndex(account => account.id === service.selectedAccountId))
    readonly property var summary: service.summary
    readonly property var artworkChoices: [{path: "", kind: "", label: "Choose local artwork"}].concat(service.artworkOptions)
    function restoreAccountSelection() {
        accountPicker.currentIndex = Qt.binding(function() { return root.selectedAccountIndex })
    }
    readonly property string snapshotAt: {
        const scanned = summary.scanned || ""
        if (!scanned) return "No snapshot yet"
        const date = new Date(scanned)
        return "Snapshot: " + (isNaN(date.getTime()) ? scanned : date.toISOString().slice(0, 16).replace("T", " ") + " UTC")
    }
    function fieldLabel(name) { return name.replace(/([a-z])([A-Z])/g, "$1 $2") }
    function positionSelection() {
        for (let i = 0; i < root.service.visibleCount; ++i) {
            if (root.service.cars.get(i).instanceId === root.service.selectedId) {
                cars.currentIndex = i
                cars.positionViewAtIndex(i, GridView.Contain)
                return
            }
        }
    }
    Component.onCompleted: Qt.callLater(positionSelection)
    Connections {
        target: root.service.cars
        function onModelReset() { Qt.callLater(root.positionSelection) }
    }
    Connections {
        target: root.service
        function onChanged() {
            if (artworkPicker.selectedCar !== root.service.selectedId) {
                artworkPicker.selectedCar = root.service.selectedId
                artworkPicker.selectedPath = ""
                artworkPicker.selectedKind = ""
                artworkPicker.currentIndex = 0
            }
        }
    }
    component CopyText: Text {
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(12)
        wrapMode: Text.Wrap
        Layout.fillWidth: true
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.px(10)
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.px(6)
            KfpsComboBox {
                id: accountPicker
                objectName: "garageAccountPicker"
                Layout.fillWidth: true
                minimumWidth: Theme.px(100)
                dense: true
                labelTextFormat: Text.PlainText
                model: root.accountChoices
                textRole: "label"
                valueRole: "id"
                currentIndex: root.selectedAccountIndex
                // ComboBox resets its index when new options retain the same selected row.
                onModelChanged: Qt.callLater(root.restoreAccountSelection)
                enabled: !root.service.busy
                Accessible.name: "FH6 account"
                toolTipText: currentIndex > 0 ? currentText : "Choose an FH6 account."
                onActivated: function(index) {
                    if (index > 0) root.service.selectAccount(root.accountChoices[index].id)
                    root.restoreAccountSelection()
                }
            }
            ToolButton {
                id: rescanButton
                objectName: "garageRescanAccounts"
                Layout.preferredWidth: Theme.px(34)
                Layout.minimumWidth: Theme.px(34)
                Layout.maximumWidth: Theme.px(34)
                Layout.preferredHeight: accountPicker.implicitHeight
                enabled: !root.service.busy && !root.service.catalogueBusy
                hoverEnabled: true
                Accessible.name: "Rescan FH6 accounts"
                contentItem: Item {
                    Icon {
                        anchors.centerIn: parent
                        name: "refresh"
                        iconSize: Theme.px(16)
                        visible: Theme.iconGlyphsVisible && GraphicsInfo.api !== GraphicsInfo.Software
                    }
                    Image {
                        anchors.centerIn: parent
                        visible: !Theme.iconGlyphsVisible || GraphicsInfo.api === GraphicsInfo.Software
                        width: Theme.px(16)
                        height: width
                        source: assetRoot + "/" + Theme.iconFolder + "/refresh.svg"
                        fillMode: Image.PreserveAspectFit
                        opacity: rescanButton.enabled ? 1 : 0.4
                    }
                }
                background: Rectangle {
                    color: rescanButton.down ? Theme.rowSelectedSurface : rescanButton.hovered ? Theme.rowHover : Theme.fieldSurface
                    radius: Theme.framedRadius(Theme.px(4))
                    border.width: 1
                    border.color: rescanButton.activeFocus ? Theme.focusColor : Theme.borderSoft
                }
                KfpsToolTip { visible: rescanButton.hovered; text: "Rescan FH6 accounts" }
                onClicked: root.service.rescanAccounts()
            }
            GhostButton {
                objectName: "garageChooseSource"
                text: "Choose File"
                iconName: "folder"
                dense: true
                toolTipText: "Choose a garage save or snapshot file."
                enabled: !root.service.busy
                onClicked: root.service.chooseSource()
            }
            GhostButton {
                objectName: "garageCancel"
                visible: root.service.busy || root.service.catalogueBusy
                text: "Cancel"
                dense: true
                iconName: "chevron-left"
                onClicked: root.service.cancel()
            }
        }
        CopyText {
            objectName: "garageAccountStatus"
            text: root.service.accountStatus
            visible: text.length > 0
            color: Theme.muted
        }
        CopyText {
            objectName: "garageCatalogueStatus"
            text: root.service.catalogueStatus
            visible: text.length > 0
            color: Theme.muted
        }
        Flow {
            objectName: "garageSummary"
            Layout.fillWidth: true
            spacing: Theme.px(14)
            visible: root.service.browseTotal > 0 || !!root.summary.scanned
            Repeater {
                model: ["Owned: " + (root.service.ownershipKnown ? (root.summary.cars || 0) : "Unknown"), "Models: " + (root.summary.models || 0),
                        "With livery: " + (root.summary.liveries || 0), "Duplicates: " + (root.summary.duplicates || 0)]
                CopyText {
                    required property string modelData
                    text: modelData
                    font.bold: true
                }
            }
        }
        CopyText {
            objectName: "garageSnapshotDate"
            visible: root.service.hasSource
            text: root.service.sourceName + " | " + root.snapshotAt
            color: Theme.muted
            font.pixelSize: Theme.px(10)
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.service.browseTotal === 0
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width, Theme.px(480))
                spacing: Theme.px(8)
                CopyText {
                    objectName: "garageEmptyTitle"
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: Theme.px(16)
                    font.bold: true
                    text: root.service.busy ? "Reading garage..." : root.summary.scanned
                          ? "No owned cars in this snapshot" : root.service.hasSource ? "No cars loaded" : "Choose an FH6 account"
                }
                CopyText {
                    objectName: "garageEmptyStatus"
                    horizontalAlignment: Text.AlignHCenter
                    color: Theme.muted
                    text: root.service.busy || root.service.hasSource ? root.service.status : "No account selected"
                }
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: root.narrow ? 2 : 3
            visible: root.service.browseTotal > 0
            KfpsTextField {
                objectName: "garageSearch"
                Layout.fillWidth: true
                Layout.columnSpan: root.narrow ? 2 : 1
                Layout.minimumWidth: 80
                placeholderText: "Search cars, copies or saved liveries"
                text: root.service.searchText
                onTextEdited: searchDelay.restart()
                Timer { id: searchDelay; interval: 150; onTriggered: root.service.setSearch(parent.text) }
            }
            KfpsComboBox {
                objectName: "garageFilter"
                Layout.fillWidth: root.narrow
                Layout.preferredWidth: Theme.px(170)
                minimumWidth: Theme.px(100)
                dense: true
                Accessible.name: "Filter cars"
                model: ["All cars", "Has livery", "Duplicate models", "Is owned"]
                currentIndex: root.service.filterIndex
                onActivated: {
                    root.service.setFilter(["all", "livery", "duplicates", "owned"][currentIndex])
                    currentIndex = Qt.binding(function() { return root.service.filterIndex })
                }
            }
            KfpsComboBox {
                objectName: "garageSort"
                Layout.fillWidth: root.narrow
                Layout.preferredWidth: Theme.px(170)
                minimumWidth: Theme.px(100)
                dense: true
                Accessible.name: "Sort cars"
                toolTipText: "Sort by name, car ownership, or available saved liveries and packages."
                model: ["Manufacturer: A to Z", "Is owned first", "Has livery first"]
                currentIndex: root.service.sortIndex
                onActivated: {
                    root.service.setSort(["name", "owned", "livery"][currentIndex])
                    currentIndex = Qt.binding(function() { return root.service.sortIndex })
                }
            }
        }
        GridLayout {
            visible: root.service.browseTotal > 0
            columns: root.narrow ? 1 : 2
            Layout.fillWidth: true
            Layout.fillHeight: true
            columnSpacing: Theme.px(16)
            rowSpacing: Theme.px(10)
            GridView {
                id: cars
                objectName: "garageCars"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: root.width * 0.68
                Layout.minimumHeight: Theme.px(130)
                clip: true
                reuseItems: true
                model: root.service.cars
                readonly property int columns: Math.max(1, Math.ceil((width - Theme.px(14)) / Theme.px(210)))
                cellWidth: Math.floor(Math.max(0, width - Theme.px(14)) / columns)
                cellHeight: cellWidth
                cacheBuffer: cellHeight
                boundsBehavior: Flickable.StopAtBounds
                keyNavigationEnabled: false
                function navigate(event, fromIndex) {
                    let next = fromIndex
                    switch (event.key) {
                    case Qt.Key_Left: next -= 1; break
                    case Qt.Key_Right: next += 1; break
                    case Qt.Key_Up: next -= columns; break
                    case Qt.Key_Down: next += columns; break
                    case Qt.Key_Home: next = 0; break
                    case Qt.Key_End: next = count - 1; break
                    default: return
                    }
                    event.accepted = true
                    if (!count) return
                    currentIndex = Math.max(0, Math.min(count - 1, next))
                    positionViewAtIndex(currentIndex, GridView.Contain)
                    if (currentItem) {
                        currentItem.forceActiveFocus(Qt.TabFocusReason)
                        root.service.select(currentItem.instanceId)
                    }
                }
                Keys.onPressed: event => navigate(event, currentIndex)
                ScrollBar.vertical: KfpsScrollBar {}
                delegate: AbstractButton {
                    id: row
                    objectName: "garageCarTile:" + instanceId
                    required property string instanceId
                    required property string title
                    required property string detail
                    required property string livery
                    required property bool hasLivery
                    required property bool owned
                    required property string thumbnailUrl
                    required property int index
                    property bool pooled: false
                    GridView.onPooled: pooled = true
                    GridView.onReused: pooled = false
                    width: Math.max(0, cars.cellWidth - Theme.px(8))
                    height: cars.cellHeight - Theme.px(8)
                    padding: Theme.px(8)
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: title + ", " + detail + (owned ? ", Owned" : root.service.ownershipKnown ? ", Not owned" : ", Ownership unknown")
                    background: Rectangle {
                        radius: Theme.framedRadius(Theme.px(4))
                        color: root.service.selectedId === row.instanceId ? Theme.rowSelectedSurface : row.hovered ? Theme.rowHover : Theme.surface
                        border.width: row.activeFocus || root.service.selectedId === row.instanceId ? 2 : 1
                        border.color: row.activeFocus || root.service.selectedId === row.instanceId ? Theme.focusColor : Theme.borderSoft
                    }
                    contentItem: Item {
                        Item {
                            objectName: "garageSquareThumbnail"
                            width: parent.width
                            height: width
                            Image {
                                id: stockImage
                                objectName: "garageStockThumbnail"
                                anchors.fill: parent
                                anchors.bottomMargin: Theme.px(70)
                                source: row.pooled ? "" : row.thumbnailUrl
                                sourceSize.width: 320
                                sourceSize.height: 180
                                asynchronous: true
                                cache: false
                                fillMode: Image.PreserveAspectFit
                            }
                            CopyText {
                                anchors.centerIn: stockImage
                                width: parent.width
                                visible: stockImage.status !== Image.Ready
                                text: stockImage.status === Image.Loading ? "Loading..." : "No stock image"
                                color: Theme.muted
                                horizontalAlignment: Text.AlignHCenter
                                font.pixelSize: Theme.px(10)
                            }
                        }
                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            spacing: Theme.px(4)
                            CopyText {
                                width: parent.width
                                height: Theme.px(32)
                                text: row.title
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                font.bold: true
                            }
                            CopyText {
                                width: parent.width
                                height: Theme.px(12)
                                text: row.detail
                                color: Theme.muted
                                font.pixelSize: Theme.px(10)
                                wrapMode: Text.NoWrap
                                elide: Text.ElideRight
                            }
                            CopyText {
                                width: parent.width
                                height: Theme.px(14)
                                text: (row.owned ? "Owned" : root.service.ownershipKnown ? "Not owned" : "Ownership unknown") + (row.hasLivery ? " | Has livery" : "")
                                color: row.owned ? Theme.text : Theme.muted
                                font.pixelSize: Theme.px(10)
                                wrapMode: Text.NoWrap
                                elide: Text.ElideRight
                            }
                        }
                    }
                    onClicked: { cars.currentIndex = index; root.service.select(instanceId) }
                    Keys.onReturnPressed: root.service.select(instanceId)
                    Keys.onEnterPressed: root.service.select(instanceId)
                    Keys.onPressed: event => cars.navigate(event, index)
                }
                CopyText {
                    anchors.centerIn: parent
                    width: Math.max(0, parent.width - Theme.px(24))
                    horizontalAlignment: Text.AlignHCenter
                    visible: cars.count === 0
                    color: Theme.muted
                    text: root.service.busy ? "Reading garage..." : root.service.total ? "No matching cars" : "No garage cars loaded"
                }
            }
            ScrollView {
                id: detailsScroll
                objectName: "garageDetails"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: root.narrow ? root.width : Theme.px(320)
                Layout.maximumWidth: root.narrow ? root.width : Theme.px(360)
                Layout.minimumHeight: Theme.px(160)
                clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: detailsScroll.availableWidth - Theme.px(14)
                    spacing: Theme.px(10)
                    CopyText { text: root.details.title; font.pixelSize: Theme.px(15); font.bold: true }
                    CopyText { text: root.details.ownership; color: Theme.muted }
                    CopyText { text: root.details.livery; color: Theme.muted }
                    GhostButton {
                        objectName: "garageOpenPreview"
                        text: "Open 3D Preview"
                        iconName: "monitor"
                        Layout.fillWidth: true
                        enabled: root.service.selectedId.length > 0 && !root.service.busy && !root.launchBusy
                        onClicked: { root.buildRequested(); root.service.openPreview() }
                    }
                    GhostButton {
                        objectName: "garageOpenStudio"
                        text: "Open in Studio"
                        iconName: "editor"
                        Layout.fillWidth: true
                        enabled: root.service.selectedId.length > 0 && !root.service.busy && !root.launchBusy
                        onClicked: { root.buildRequested(); root.service.openStudio() }
                    }
                    CopyText { text: root.details.owned ? "Current body build / No artwork" : "Stock body / No artwork"; color: Theme.muted }
                    KfpsComboBox {
                        id: artworkPicker
                        objectName: "garageArtworkPicker"
                        property string selectedCar: root.service.selectedId
                        property string selectedPath: ""
                        property string selectedKind: ""
                        Layout.fillWidth: true
                        visible: root.details.owned
                        enabled: !root.service.busy && !root.launchBusy && root.artworkChoices.length > 1
                        model: root.artworkChoices
                        textRole: "label"
                        labelTextFormat: Text.PlainText
                        onModelChanged: Qt.callLater(function() {
                            currentIndex = Math.max(0, root.artworkChoices.findIndex(choice =>
                                choice.path === selectedPath && choice.kind === selectedKind))
                        })
                        onActivated: function(index) {
                            const choice = root.artworkChoices[index]
                            selectedPath = choice ? choice.path : ""
                            selectedKind = choice ? choice.kind : ""
                        }
                    }
                    GhostButton {
                        objectName: "garageOpenArtwork"
                        text: "Open Artwork in Studio"
                        iconName: "editor"
                        Layout.fillWidth: true
                        visible: root.details.owned
                        enabled: artworkPicker.currentIndex > 0 && !root.service.busy && !root.launchBusy
                        onClicked: {
                            const choice = root.artworkChoices[artworkPicker.currentIndex]
                            root.buildRequested()
                            root.service.openArtwork(choice.path, choice.kind)
                        }
                    }
                    GhostButton {
                        objectName: "garageOpenLivery"
                        text: "Show Applied Livery"
                        iconName: "folder"
                        Layout.fillWidth: true
                        enabled: root.details.matched && !root.service.busy
                        onClicked: root.service.openLivery()
                    }
                    CopyText { text: root.details.reference; color: Theme.muted }
                    CopyText { text: root.details.tune; color: Theme.muted }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
                    GhostButton {
                        text: "Saved part IDs"
                        iconName: root.showParts ? "chevron-left" : "chevron-right"
                        dense: true
                        enabled: root.details.owned
                        onClicked: root.showParts = !root.showParts
                    }
                    Repeater {
                        model: root.showParts ? root.details.parts : []
                        RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            CopyText { text: root.fieldLabel(modelData.name); color: Theme.muted }
                            CopyText { text: modelData.value; Layout.fillWidth: false; Layout.preferredWidth: Theme.px(85); horizontalAlignment: Text.AlignRight }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        GhostButton {
                            objectName: "garageCompare"
                            text: "Compare From Here"
                            iconName: "source-check"
                            enabled: root.details.owned
                            onClicked: root.service.pinComparison()
                        }
                        GhostButton {
                            text: "Clear"
                            iconName: "chevron-left"
                            visible: root.service.compareLabel.length > 0
                            onClicked: root.service.clearComparison()
                        }
                    }
                    CopyText {
                        visible: root.service.compareLabel.length > 0
                        text: "Compared with " + root.service.compareLabel
                        color: Theme.muted
                    }
                    Repeater {
                        model: root.service.differences
                        CopyText {
                            required property var modelData
                            text: root.fieldLabel(modelData.field) + ": " + modelData.before + " -> " + modelData.after
                        }
                    }
                    CopyText {
                        visible: root.service.compareLabel.length > 0 && root.service.differences.length === 0
                        text: "No saved-build differences"
                        color: Theme.muted
                    }
                    CopyText { text: "Saved comparisons"; font.bold: true }
                    KfpsComboBox {
                        objectName: "garageSavedComparisons"
                        labelTextFormat: Text.PlainText
                        Layout.fillWidth: true
                        model: [{id: "", name: "Choose comparison"}].concat(root.service.savedComparisons)
                        textRole: "name"
                        enabled: !root.service.busy
                        currentIndex: Math.max(0, model.findIndex(item => item.id === root.service.savedComparisonId))
                        onActivated: root.service.chooseComparison(model[currentIndex].id)
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        GhostButton {
                            objectName: "garageSaveComparison"
                            text: "Save Comparison"
                            iconName: "json"
                            dense: true
                        enabled: root.details.owned && !root.service.busy
                            onClicked: comparisonName.open()
                        }
                        GhostButton {
                            objectName: "garageRemoveComparison"
                            text: "Remove"
                            dense: true
                            enabled: root.service.savedComparisonId.length > 0 && !root.service.busy
                            onClicked: removeComparison.open()
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: root.service.savedComparisonId.length > 0
                        GhostButton {
                            objectName: "garageLinkProject"
                            text: root.service.projectLinked ? "Relink Studio Project" : "Link Studio Project"
                            iconName: "folder"
                            Layout.fillWidth: true
                            enabled: !root.service.busy
                            onClicked: root.service.chooseProject()
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: root.service.projectLinked
                            GhostButton {
                                objectName: "garageCheckProject"
                                text: "Check Project"
                                iconName: "refresh"
                                dense: true
                                enabled: !root.service.busy
                                onClicked: root.service.checkProject()
                            }
                            GhostButton {
                                objectName: "garageShowProject"
                                text: "Show Folder"
                                iconName: "folder"
                                dense: true
                                enabled: !root.service.busy
                                onClicked: root.service.revealProject()
                            }
                        }
                        GhostButton {
                            objectName: "garageOpenProject"
                            text: "Open Linked Project"
                            iconName: "editor"
                            Layout.fillWidth: true
                            visible: root.service.projectLinked
                            enabled: !root.service.busy && !root.launchBusy
                            onClicked: { root.buildRequested(); root.service.openProject() }
                        }
                        CopyText { text: root.service.projectStatus; color: Theme.muted }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
                    KfpsCheckBox {
                        objectName: "garageHistoryToggle"
                        text: "Keep local change history"
                        checked: root.service.historyEnabled
                        enabled: !root.service.busy && (root.service.historyAvailable || checked)
                        onClicked: root.service.setHistoryEnabled(checked)
                    }
                    CopyText {
                        visible: root.service.total > 0 && !root.service.historyAvailable
                        text: "Snapshot only; profile continuity is unverified."
                        color: Theme.muted
                    }
                    Repeater {
                        model: root.service.history
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            CopyText { text: modelData.at + " / " + modelData.count + " changed cars"; font.bold: true }
                            Repeater {
                                model: modelData.changes
                                CopyText {
                                    required property var modelData
                                    text: "Car " + modelData.carId + " / Copy " + modelData.instanceId + ": " + modelData.fields.map(root.fieldLabel).join(", ")
                                    color: Theme.muted
                                }
                            }
                        }
                    }
                    CopyText { text: root.details.scanned; color: Theme.muted; font.pixelSize: Theme.px(10) }
                }
            }
        }
    }
    Dialog {
        id: comparisonName
        title: "Save Comparison"
        modal: true
        anchors.centerIn: parent
        width: Math.min(root.width - Theme.px(24), Theme.px(360))
        standardButtons: Dialog.Save | Dialog.Cancel
        onOpened: { nameInput.text = ""; nameInput.forceActiveFocus() }
        onAccepted: root.service.saveComparison(nameInput.text)
        contentItem: KfpsTextField {
            id: nameInput
            objectName: "garageComparisonName"
            placeholderText: "Comparison name"
            maximumLength: 80
        }
    }
    Dialog {
        id: removeComparison
        objectName: "garageRemoveComparisonDialog"
        title: "Remove Saved Comparison?"
        modal: true
        anchors.centerIn: parent
        width: Math.min(root.width - Theme.px(24), Theme.px(360))
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: root.service.removeComparison()
        contentItem: Item {
            implicitHeight: removalMessage.implicitHeight
            CopyText {
                id: removalMessage
                width: removeComparison.availableWidth
                color: removeComparison.palette.windowText
                text: "Only this comparison and its project link will be removed. The project file will not be changed."
            }
        }
    }
}
