import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root

    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 980
    property bool compact: Theme.logical(width) < 760
    readonly property bool headerAlignmentAvailable: root.wide
                                                     && communityCard.width > 0
                                                     && specialThanksCard.width > 0
    readonly property real headerSourceCenterX: communityGrid.x + communityCard.x + communityCard.width / 2
    readonly property real headerPreviewCenterX: communityGrid.x + specialThanksCard.x + specialThanksCard.width / 2
    readonly property real headerBannerLeftX: communityGrid.x + communityCard.x
    readonly property real headerBannerRightX: communityGrid.x + specialThanksCard.x + specialThanksCard.width

    readonly property var projectCredits: [
        {
            name: "AE / A-Dawg#0001",
            link: "https://github.com/forza-painter/forza-painter",
            role: "Original Forza Painter project",
            detail: "MIT-licensed import workflow, memory-writing/import foundation, and the geometry-to-vinyl approach that KFPS builds from."
        },
        {
            name: "BVZRays / bvz rays",
            link: "https://github.com/bvzrays/forza-painter-fh6",
            role: "FH6 desktop workflow and experimentation",
            detail: "FH6-focused desktop work, importer and locator behavior, UI/package workflow ideas, and upstream FH6 testing direction."
        },
        {
            name: "Arstz / ForzaLiveryStudio",
            link: "https://github.com/Arstz/ForzaLiveryStudio",
            role: "Public Forza save-format research",
            detail: "Documentation and save-file-first research helped clarify KFPS offline library work, especially around groups, liveries, headers, and local save structure."
        },
        {
            name: "Fabric.js",
            link: "https://fabricjs.com/",
            role: "Bundled browser editor foundation",
            detail: "Canvas editing library used by the included editor workflow."
        },
        {
            name: "zjl88858 / forza-painter-geometrize-gpu",
            link: "https://github.com/zjl88858/forza-painter-geometrize-gpu",
            role: "GPU/OpenCL generator lineage",
            detail: "Generator lineage used by the bundled generation workflow."
        },
        {
            name: "Sam Twidale",
            link: "https://samcodes.co.uk/",
            role: "geometrize-lib author",
            detail: "Original geometry approximation work credited by upstream license notices."
        },
        {
            name: "Michael Fogleman",
            link: "https://github.com/fogleman/primitive",
            role: "primitive author",
            detail: "Original primitive-based image approximation library credited by upstream license notices."
        },
        {
            name: "Sanguk Ko / ree9622",
            link: "https://github.com/ree9622",
            role: "Localization contributor",
            detail: "Korean localization contributor in upstream history."
        },
        {
            name: "heyitshestia / Kloudy",
            link: "https://github.com/heyitshestia/kloudys-forza-painter-suite",
            role: "KFPS suite",
            detail: "Suite workflow, native QML app, presets, finalization, JSON browser, updater, packaging, FH6 safety adjustments, layer culling, editor integration, and FH6 handmade/import tooling."
        }
    ]

    readonly property var flsCredits: [
        {
            name: "Arstz",
            link: "https://github.com/Arstz",
            detail: "Project author/maintainer, C++/Qt editor work, proprietary Forza binary import/export direction, documentation, and overall architecture."
        },
        {
            name: "Fr4g3z",
            link: "https://github.com/Fr4g3z",
            detail: "Format reversing help and editor/tooling contributions including color sampling and quality-of-life work."
        },
        {
            name: "RPINerd",
            link: "https://github.com/RPINerd",
            detail: "Linux build documentation and build-fix contributions."
        },
        {
            name: "Zloysvin",
            link: "",
            detail: "Forza Motorsport save and livery investigation support."
        },
        {
            name: "Pengyss",
            link: "",
            detail: "Research and validation help around livery data behavior."
        },
        {
            name: "Mixbob",
            link: "",
            detail: "Testing and sample data that helped public ForzaLiveryStudio work move forward."
        },
        {
            name: "Eaterrius",
            link: "",
            detail: "Testing and validation support in the ForzaLiveryStudio research history."
        }
    ]

    readonly property var communityNames: [
        "LanceMuscles", "River", "Elu", "Wolfie", "WKD_Will", "Big Nut",
        "Korinthian", "Catinus", "Soypoka", "Slasher", "Melon", "Eddie",
        "Frozander", "Kuroshine", "slaigh.", "Asayunon", "Astral_Cat",
        "dcinside.com", "minnn"
    ]

    readonly property var flsNames: [
        "Arstz", "Fr4g3z", "RPINerd", "Zloysvin", "Pengyss", "Mixbob",
        "Eaterrius"
    ]

    FastScrollView {
        id: scroll

        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            id: pageColumn

            width: scroll.availableWidth
            spacing: Theme.px(14)

            HoverCard {
                Layout.fillWidth: true
                Layout.preferredHeight: heroContent.implicitHeight + Theme.px(36)
                padding: Theme.px(18)
                strong: true

                ColumnLayout {
                    id: heroContent

                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    spacing: Theme.px(10)

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.px(12)

                        Rectangle {
                            Layout.preferredWidth: Theme.px(root.compact ? 44 : 54)
                            Layout.preferredHeight: Layout.preferredWidth
                            radius: width / 2
                            color: Theme.logoCapsuleSurface
                            border.width: Math.max(1, Theme.px(1))
                            border.color: Theme.primaryBright
                            antialiasing: true

                            Icon {
                                anchors.centerIn: parent
                                name: "heart"
                                iconSize: Theme.px(root.compact ? 22 : 28)
                                glow: true
                            }
                        }

                        SectionHeading {
                            Layout.fillWidth: true
                            title: "Credits"
                            subtitle: "KFPS stands on years of Forza Painter research, generator work, editor tooling, testing, and community guidance."
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "This page collects the same credits that belong in the repository, but makes them visible inside the app where users actually spend time. It separates original project lineage, public research, generator foundations, editor tooling, community testing, and license notices so the chain of work stays clear."
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        wrapMode: Text.WordWrap
                        lineHeight: 1.32
                        lineHeightMode: Text.ProportionalHeight
                    }
                }
            }

            GridLayout {
                id: communityGrid
                Layout.fillWidth: true
                columns: root.wide ? 2 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(12)

                HoverCard {
                    id: communityCard
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(communityContent.implicitHeight, flsOverviewContent.implicitHeight) + Theme.px(32)
                    Layout.alignment: Qt.AlignTop
                    padding: Theme.px(16)
                    soft: true

                    ColumnLayout {
                        id: communityContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: Theme.px(8)

                        Text {
                            Layout.fillWidth: true
                            text: "Community Contributions"
                            color: Theme.primaryBright
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(17)
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "A very, very big thank you to LanceMuscles for insights into the deep and almost forgotten lore of Forza Horizon image-to-vinyl generation."
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.4)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.3
                            lineHeightMode: Text.ProportionalHeight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "More thanks to River, Elu, Wolfie, WKD_Will, Big Nut, Korinthian, Catinus, Soypoka, Slasher, Melon, Eddie, Frozander, Kuroshine, slaigh., Asayunon, and Astral_Cat for suggestions, testing, tips, and solutions. Thank you to dcinside.com and minnn for detailed guide coverage and feedback."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.6)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: Theme.px(7)

                            Repeater {
                                model: root.communityNames

                                delegate: Rectangle {
                                    required property string modelData

                                    width: nameText.implicitWidth + Theme.px(18)
                                    height: Theme.px(28)
                                    radius: height / 2
                                    color: Theme.logoCapsuleSurface
                                    border.width: Math.max(1, Theme.px(1))
                                    border.color: Theme.borderSoft

                                    Text {
                                        id: nameText

                                        anchors.centerIn: parent
                                        text: modelData
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(10.7)
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }
                    }
                }

                HoverCard {
                    id: specialThanksCard
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(communityContent.implicitHeight, flsOverviewContent.implicitHeight) + Theme.px(32)
                    Layout.alignment: Qt.AlignTop
                    padding: Theme.px(16)
                    strong: true

                    ColumnLayout {
                        id: flsOverviewContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: Theme.px(8)

                        Text {
                            Layout.fillWidth: true
                            text: "Special Thanks: ForzaLiveryStudio"
                            color: Theme.primaryBright
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(17)
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                        }

                        Text {
                            Layout.fillWidth: true
                            Layout.minimumHeight: Math.ceil(paintedHeight)
                            text: "KFPS' offline save-library direction was informed by studying the public ForzaLiveryStudio project, especially its documented C_group, C_livery, header, and save-file-first approach."
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12.4)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.3
                            lineHeightMode: Text.ProportionalHeight
                        }

                        KfpsLinkText {
                            Layout.fillWidth: true
                            text: "Open ForzaLiveryStudio on GitHub"
                            url: "https://github.com/Arstz/ForzaLiveryStudio"
                            toolTipText: "Open the public ForzaLiveryStudio repository used for research reference."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.6)
                            font.weight: Font.DemiBold
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "The important value was research direction, not copied implementation: how local save data is treated as structured records, how groups and liveries are separated conceptually, why headers and library entries matter, and why offline import/export behavior needs its own dedicated path instead of being patched into the live memory route."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.6)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "KFPS does not vendor ForzaLiveryStudio code. This credit is for public documentation, format investigation, examples, and architecture signals that made the offline route clearer and easier to validate."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.6)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: Theme.px(7)

                            Repeater {
                                model: root.flsNames

                                delegate: Rectangle {
                                    id: flsNameChip

                                    required property string modelData

                                    width: flsNameText.implicitWidth + Theme.px(18)
                                    height: Theme.px(28)
                                    radius: height / 2
                                    color: Theme.logoCapsuleSurface
                                    border.width: Math.max(1, Theme.px(1))
                                    border.color: Theme.borderSoft

                                    Text {
                                        id: flsNameText

                                        anchors.centerIn: parent
                                        text: flsNameChip.modelData
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(10.7)
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }
                    }
                }
            }

            SectionHeading {
                Layout.fillWidth: true
                title: "Project Lineage"
                subtitle: "Core projects and people credited for the workflow foundations, generator lineage, editor tooling, localization history, and KFPS suite work."
            }

            Repeater {
                model: root.projectCredits

                delegate: HoverCard {
                    id: creditCard

                    required property var modelData

                    Layout.fillWidth: true
                    Layout.preferredHeight: creditContent.implicitHeight + Theme.px(28)
                    padding: Theme.px(14)
                    soft: true

                    ColumnLayout {
                        id: creditContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: Theme.px(5)

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(8)

                            KfpsLinkText {
                                Layout.fillWidth: true
                                text: creditCard.modelData.name
                                url: creditCard.modelData.link
                                toolTipText: url.length > 0 ? "Open the credited project or contributor page." : ""
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(13.2)
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                            }

                            Text {
                                Layout.preferredWidth: Theme.px(root.compact ? 118 : 210)
                                text: creditCard.modelData.role
                                color: Theme.subtle
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(10.7)
                                horizontalAlignment: Text.AlignRight
                                wrapMode: Text.Wrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: creditCard.modelData.detail
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.3)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: root.wide ? 2 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(12)

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: flsDetailContent.implicitHeight + Theme.px(32)
                    padding: Theme.px(16)
                    soft: true

                    ColumnLayout {
                        id: flsDetailContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: Theme.px(8)

                        Text {
                            Layout.fillWidth: true
                            text: "Additional ForzaLiveryStudio Thanks"
                            color: Theme.primaryBright
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(16.5)
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                        }

                        Repeater {
                            model: root.flsCredits

                            delegate: ColumnLayout {
                                required property var modelData

                                width: flsDetailContent.width
                                spacing: Theme.px(2)

                                KfpsLinkText {
                                    Layout.fillWidth: true
                                    text: modelData.name
                                    url: modelData.link
                                    toolTipText: url.length > 0 ? "Open this contributor's public profile." : ""
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(11.6)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.detail
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(10.6)
                                    wrapMode: Text.WordWrap
                                    lineHeight: 1.22
                                    lineHeightMode: Text.ProportionalHeight
                                }
                            }
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: noticesContent.implicitHeight + Theme.px(32)
                    padding: Theme.px(16)
                    soft: true

                    ColumnLayout {
                        id: noticesContent

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: Theme.px(8)

                        Text {
                            Layout.fillWidth: true
                            text: "License Notices"
                            color: Theme.primaryBright
                            font.family: Theme.displayFamily
                            font.pixelSize: Theme.px(16.5)
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "KFPS keeps project and third-party notices in LICENSE, LICENSE.geometrize-gpu, LICENSE.custom-importer, and LICENSE.fabricjs."
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(12)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.3
                            lineHeightMode: Text.ProportionalHeight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "The custom handmade/import tooling carries its own attribution notice. The bundled Fabric.js library is credited separately. Generator and geometry approximation notices remain attached to their upstream lineage."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11.2)
                            wrapMode: Text.WordWrap
                            lineHeight: 1.28
                            lineHeightMode: Text.ProportionalHeight
                        }
                    }
                }
            }
        }
    }
}
