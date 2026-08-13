# 07/10~12 클래스 명단 및 정제 과정

대상: **07/10~12 non-DoH 전량 1,329,864세션**. (DoH 포함/제외로 클래스 수는 동일)

## 요약
| 단계 | 클래스 수 | 감소 |
|---|--:|--:|
| ① raw task3 (원본 폴더 라벨) | 136 | — |
| ② 정규화 (표기 통일) | 132 | −4 |
| ③ 희소 제외 (세션 <5) | 111 | −21 |

→ 최종 학습 클래스 = **111개**

## ①→② 정규화로 병합된 그룹 (136→132, 총 −4)
여러 raw 표기가 하나의 정규화 라벨로 합쳐진 경우:

| 정규화 라벨 | ← 합쳐진 raw task3들 |
|---|---|
| `firefox` | `Firefox`, `firefox.exe` |
| `league_of_legends` | `League_of_Legends`, `league of legends.exe` |
| `mupdate2` | `MUpdate2`, `mupdate2.exe` |
| `riot_client` | `RiotClient`, `Riot_Client` |

## ②→③ 희소(<5 세션)로 제외된 클래스 (132→111, 총 −21)
| 클래스 | 세션수 |
|---|--:|
| `cowork_svc` | 4 |
| `adobearm` | 4 |
| `softlandingtask` | 4 |
| `whatsapp.root` | 4 |
| `squirrel` | 3 |
| `zoom` | 3 |
| `agsservice` | 3 |
| `powertoys` | 3 |
| `onedrivelauncher` | 3 |
| `lghub_agent` | 3 |
| `sysmon` | 2 |
| `wscript` | 2 |
| `alpdf` | 2 |
| `textinputhost` | 1 |
| `ms_teamsupdate` | 1 |
| `postman_agent` | 1 |
| `ngm64` | 1 |
| `officesvcmgr` | 1 |
| `core_temp` | 1 |
| `ruximics` | 1 |
| `upfc` | 1 |

## 최종 111개 클래스 (세션수 내림차순)
| # | 클래스 | 세션수 |
|--:|---|--:|
| 1 | `svchost` | 499,093 |
| 2 | `google_chrome` | 201,217 |
| 3 | `system` | 122,781 |
| 4 | `servicemapcollector` | 58,324 |
| 5 | `claude` | 48,078 |
| 6 | `notion` | 42,736 |
| 7 | `riot_client` | 39,492 |
| 8 | `chrome_원격_데스크톱` | 34,483 |
| 9 | `visual_studio` | 29,989 |
| 10 | `nexonplug` | 27,869 |
| 11 | `microsoft_edge` | 22,492 |
| 12 | `unknown` | 16,400 |
| 13 | `codex` | 16,078 |
| 14 | `spotify` | 14,884 |
| 15 | `discord` | 14,340 |
| 16 | `parsec` | 12,408 |
| 17 | `chatgpt` | 11,335 |
| 18 | `microsoft_onedrive` | 10,376 |
| 19 | `fclauncher` | 9,771 |
| 20 | `steam` | 9,062 |
| 21 | `visual_studio_code` | 7,003 |
| 22 | `xshell` | 6,638 |
| 23 | `genspark_claw` | 6,231 |
| 24 | `mpdefendercoreservice` | 6,105 |
| 25 | `notion_calendar` | 5,646 |
| 26 | `slack` | 5,305 |
| 27 | `kakaotalk` | 4,804 |
| 28 | `microsoft_office` | 4,791 |
| 29 | `nvidia_overlay` | 4,143 |
| 30 | `nvcontainer` | 3,975 |
| 31 | `antigravity` | 3,178 |
| 32 | `autolabellauncher` | 3,090 |
| 33 | `asd_framework` | 2,892 |
| 34 | `nliveconnector` | 2,107 |
| 35 | `socketlogger` | 2,047 |
| 36 | `gamingservices` | 1,884 |
| 37 | `works` | 1,856 |
| 38 | `dashost` | 1,849 |
| 39 | `microsoft_365_copilot` | 1,759 |
| 40 | `microsoft_teams` | 1,716 |
| 41 | `microsoft_intune` | 1,217 |
| 42 | `leagueclient` | 1,154 |
| 43 | `backgroundtaskhost` | 960 |
| 44 | `fczf` | 805 |
| 45 | `league_of_legends` | 672 |
| 46 | `widgets` | 671 |
| 47 | `taskhostw` | 572 |
| 48 | `microsoft_365_and_office` | 541 |
| 49 | `firefox` | 466 |
| 50 | `vgc` | 410 |
| 51 | `adobecollabsync` | 406 |
| 52 | `acrotray` | 316 |
| 53 | `msmpeng` | 295 |
| 54 | `flexnet_publisher_32_bit` | 292 |
| 55 | `explorer` | 281 |
| 56 | `searchapp` | 187 |
| 57 | `ssh` | 153 |
| 58 | `searchhost` | 142 |
| 59 | `game_bar` | 130 |
| 60 | `nosstarter.npe` | 129 |
| 61 | `mousocoreworker` | 117 |
| 62 | `soopstreamer` | 104 |
| 63 | `microsoft_phone_link` | 98 |
| 64 | `nossvc` | 95 |
| 65 | `google_updater_x64` | 87 |
| 66 | `nvidia_app` | 72 |
| 67 | `acrobat` | 71 |
| 68 | `nvdisplay.container` | 71 |
| 69 | `vanguard_tray` | 69 |
| 70 | `startmenuexperiencehost` | 66 |
| 71 | `hncupdateservice` | 61 |
| 72 | `python` | 53 |
| 73 | `onedrivesetup` | 52 |
| 74 | `acrocef` | 51 |
| 75 | `ahnlab_safe_transaction` | 47 |
| 76 | `sihclient` | 46 |
| 77 | `omadmclient` | 43 |
| 78 | `lockapp` | 42 |
| 79 | `backgroundtransferhost` | 41 |
| 80 | `clientcertcheck` | 38 |
| 81 | `backgrounddownload` | 37 |
| 82 | `lsass` | 35 |
| 83 | `smartscreen` | 32 |
| 84 | `spotifyxboxgamebarwebview` | 27 |
| 85 | `adnotificationmanager` | 26 |
| 86 | `clienthealtheval` | 26 |
| 87 | `mupdate2` | 25 |
| 88 | `microsoft_desktop_app_installer` | 23 |
| 89 | `mcupdatermodule` | 22 |
| 90 | `crossdeviceservice` | 22 |
| 91 | `adobegcclient` | 20 |
| 92 | `officec2rclient` | 17 |
| 93 | `windows_subsystem_for_linux` | 14 |
| 94 | `logioptionsplus_updater` | 12 |
| 95 | `compattelrunner` | 12 |
| 96 | `gamebarpresencewriter` | 11 |
| 97 | `hpprinterhealthmonitor` | 10 |
| 98 | `shellexperiencehost` | 10 |
| 99 | `systemsettings` | 9 |
| 100 | `desktopcal` | 9 |
| 101 | `wshelper` | 9 |
| 102 | `bandizip` | 8 |
| 103 | `wmiprvse` | 7 |
| 104 | `npupdatec` | 6 |
| 105 | `windows_search` | 6 |
| 106 | `wstoastnotification` | 6 |
| 107 | `xbox_app` | 5 |
| 108 | `rundll32` | 5 |
| 109 | `actionsserver` | 5 |
| 110 | `claude_setup` | 5 |
| 111 | `winword` | 5 |
