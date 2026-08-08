# SDX2 limits — ripped from lomdar.com core planner

Source: `https://www.lomdar.com/games/se1/data/sdx2.json` (the planner at `/games/se1/sdx2/planner/` fetches this).

- modset: **SDX 2**
- gameBuild: **01_210_012**
- generated: **2026-08-07**
- schema: 1

## World speed

**`worldSpeed = 1000` m/s** — the SCF `MaxPossibleSpeedMetersPerSecond`. Per-class caps below are absolute m/s, not modifiers.

## Ship classes

| core | subtype | class | max speed | backup cores | grid |
|---|---|---|---|---|---|
| **Skiff** | `sdx_shipcoreNoCore` | None | **400** | 0 | — |
| **Barge** | `sdx_shipcoreBarge` | Civilian | **300** | 10 | Large |
| **Hauler** | `sdx_shipcoreHauler` | Civilian | **300** | 10 | Large |
| **Picket** | `sdx_shipcorePicket` | Combat | **650** | 10 | Large |
| **Corvette** | `sdx_shipcoreCorvette` | Combat | **550** | 10 | Large |
| **Frigate** | `sdx_shipcoreFrigate` | Combat | **500** | 10 | Large |
| **Cruiser** | `sdx_shipcoreCruiser` | Combat | **450** | 10 | Large |
| **Carrier** | `sdx_shipcoreCarrier` | Combat | **300** | 10 | Large |
| **Outpost** | `sdx_shipcoreOutpost` | Station | **50** | unlimited | Large |
| **Installation** | `sdx_shipcoreInstallation` | Station | **50** | unlimited | Large |

## Category budgets by class

`—` = category absent for that core. `0` = present but banned. `*` suffix = critical (losing it triggers the punishment).

| category | Skiff | Barge | Hauler | Picket | Corvette | Frigate | Cruiser | Carrier | Outpost | Installation |
|---|---|---|---|---|---|---|---|---|---|---|
| Offensive Weapons | 0 | 0 | 0 | 56 | 62* | 90* | 102* | 102 | 0 | 0 |
| Point Defense Cannons | 2* | 8* | 16* | 5 | 8* | 12* | 26* | 20* | 10* | 20 |
| Advanced Point Defense Cannons | 0 | — | — | — | — | — | — | — | — | — |
| Torpedo Launchers | 0 | — | — | 14 | 28* | 56* | 70* | 70 | 0 | 0 |
| Fixed Railguns | 0 | — | — | 0 | 1* | 2* | 2* | 2 | — | — |
| Turreted Railguns | 0 | — | — | 0 | 0 | 0 | 1* | 1 | 0 | 2 |
| Epstein Drives | 2* | 12 | 36* | 1 | 2* | 4* | 8* | 36 | 4 | 8 |
| Power Blocks | 4* | 7* | 13* | 6 | 9* | 13* | 25* | 25* | 25* | 37 |
| Tools | 6 | — | 0 | 0 | — | — | — | — | — | — |
| Hangars | 0 | — | 0 | 0 | 0 | 0 | 1 | — | 2* | 12* |
| Utilities | 15* | 40* | 100 | 15 | 25* | 50* | 70* | 150* | — | — |
| Military Epstein Drives | 0 | 0 | 0 | — | — | — | — | — | — | — |
| Storage | 104* | 750* | 2250 | 24 | 40 | 75 | 155 | 750* | 1000* | 4000* |
| Directional Sensors | 0 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | — | — |
| Radar | 0 | 0 | — | — | — | — | — | 1 | — | — |
| Basic Production | 2 | — | — | — | — | — | — | — | — | — |
| Production | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 5 | 20 |
| O2/H2O Generators | 0 | 0 | — | — | — | — | — | — | — | — |
| Warheads | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Ship Cores | — | 10* | 10* | 10 | 10* | 10* | 10* | 10* | — | — |
| Advanced Production | — | 0 | — | — | — | — | — | 0 | 0 | — |
| Grinders and Drills | — | 6 | — | — | — | — | — | — | — | — |
| Welders | — | 0 | — | — | — | — | — | — | — | — |
| Civilian Hangars | — | 2* | — | — | — | — | — | 0 | — | 0 |
| Military Hangars | — | 0 | — | — | — | — | 0 | 8* | — | — |
| Focused Sensors | — | 0 | 0 | — | — | 0 | 0 | 0 | — | — |
| Passive Directional Multi-band Sensor | — | 0 | — | 0 | 0 | 0 | — | — | — | — |
| Small Radar | — | — | 1 | 1 | 1 | 1 | 1 | — | — | — |
| Large Radar | — | — | 0 | 0 | 0 | 0 | 0 | — | — | — |
| Ceramics | — | — | — | 20 | 40* | 60* | 120* | 240* | — | — |
| Solar Panels | — | — | — | 0 | 0* | 0 | 0 | 0 | — | — |
| Ore Detectors | — | — | — | 0 | 0 | 0 | 0 | 0 | — | — |
| Welders and Drills | — | — | — | — | 0 | 0 | 0 | 0 | — | — |
| Grinders | — | — | — | — | 1 | 2 | 4 | 6 | — | — |
| Multi-Directional Sensors | — | — | — | — | — | — | 5 | 5 | — | — |
| Welders Grinders | — | — | — | — | — | — | — | — | 6 | — |
| Drills | — | — | — | — | — | — | — | — | 0 | 0 |
| Station Hangars | — | — | — | — | — | — | — | — | 0 | — |
| Welders and Grinders | — | — | — | — | — | — | — | — | — | 12 |

## Category detail (groups, directions, punishment)

### Skiff  (None, 400 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Offensive Weapons | 0 |  | ShutOff | — | `weapons` |
| Point Defense Cannons | 2 | yes | ShutOff | — | `pdcsEvenAdvWeights` |
| Advanced Point Defense Cannons | 0 |  | ShutOff | — | `pdcsAdv` |
| Torpedo Launchers | 0 |  | ShutOff | — | `torpedoLaunchers` |
| Fixed Railguns | 0 |  | ShutOff | — | `railgunsFixed` |
| Turreted Railguns | 0 |  | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 2 | yes | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial` |
| Power Blocks | 4 | yes | ShutOff | — | `powerBlocksCivilian`, `solarPanels` |
| Tools | 6 |  | ShutOff | — | `Welders`, `Drills`, `Grinders` |
| Hangars | 0 |  | ShutOff | — | `hangarsCivilian`, `hangarsMilitary` |
| Utilities | 15 | yes | ShutOff | — | `Gyroscopes`, `Decoys` |
| Military Epstein Drives | 0 |  | ShutOff | Backward | `epsteinDrivesMilitary` |
| Storage | 104 | yes | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Directional Sensors | 0 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalDirectional`, `sdx_sensorsOpticalFocused`, `sdx_sensorsMultiDirectional` |
| Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar1x1`, `sdx_sensorsRadar2x2` |
| Basic Production | 2 |  | ShutOff | — | `productionBasic` |
| Production | 0 |  | ShutOff | — | `production`, `productionAdvanced` |
| O2/H2O Generators | 0 |  | ShutOff | — | `productionWater` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Barge  (Civilian, 300 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Point Defense Cannons | 8 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Epstein Drives | 12 |  | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial` |
| Military Epstein Drives | 0 |  | ShutOff | Backward | `epsteinDrivesMilitary` |
| Power Blocks | 7 | yes | ShutOff | — | `powerBlocksCivilian`, `solarPanels` |
| Offensive Weapons | 0 |  | ShutOff | — | `weapons` |
| Ship Cores | 10 | yes | ShutOff | Forward | `sdx_shipcores` |
| Storage | 750 | yes | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 2 |  | ShutOff | — | `production`, `productionBasic` |
| Advanced Production | 0 |  | ShutOff | — | `productionAdvanced` |
| O2/H2O Generators | 0 |  | ShutOff | — | `productionWater` |
| Grinders and Drills | 6 |  | ShutOff | — | `Grinders`, `Drills` |
| Welders | 0 |  | ShutOff | — | `Welders` |
| Civilian Hangars | 2 | yes | ShutOff | — | `hangarsCivilian` |
| Military Hangars | 0 |  | ShutOff | — | `hangarsMilitary`, `hangarsStation` |
| Utilities | 40 | yes | ShutOff | — | `Gyroscopes`, `Decoys` |
| Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar1x1`, `sdx_sensorsRadar2x2` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsOpticalDirectional` |
| Focused Sensors | 0 |  | ShutOff | — | `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalFocused` |
| Passive Directional Multi-band Sensor | 0 |  | ShutOff | — | `sdx_sensorsMultiDirectional` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Hauler  (Civilian, 300 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Offensive Weapons | 0 |  | Delete | — | `weapons` |
| Point Defense Cannons | 16 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Epstein Drives | 36 | yes | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial` |
| Military Epstein Drives | 0 |  | ShutOff | Backward | `epsteinDrivesMilitary` |
| Power Blocks | 13 | yes | ShutOff | — | `powerBlocksCivilian`, `solarPanels` |
| Ship Cores | 10 | yes | ShutOff | Forward | `sdx_shipcores` |
| Storage | 2250 |  | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 0 |  | ShutOff | — | `production`, `productionBasic`, `productionAdvanced` |
| Tools | 0 |  | ShutOff | — | `Welders`, `Drills`, `Grinders` |
| Hangars | 0 |  | ShutOff | — | `hangarsCivilian`, `hangarsMilitary`, `hangarsStation` |
| Utilities | 100 |  | ShutOff | — | `Gyroscopes`, `Decoys` |
| Small Radar | 1 |  | ShutOff | — | `sdx_sensorsRadar1x1` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsOpticalDirectional` |
| Large Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar2x2` |
| Focused Sensors | 0 |  | ShutOff | — | `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalFocused` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Picket  (Combat, 650 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Ceramics | 20 |  | Delete | — | `ceramics` |
| Offensive Weapons | 56 |  | ShutOff | — | `weapons` |
| Point Defense Cannons | 5 |  | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 14 |  | ShutOff | — | `torpedoLaunchers` |
| Fixed Railguns | 0 |  | ShutOff | — | `railgunsFixed` |
| Turreted Railguns | 0 |  | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 1 |  | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Power Blocks | 6 |  | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian` |
| Solar Panels | 0 |  | ShutOff | — | `solarPanels` |
| Ship Cores | 10 |  | ShutOff | Forward | `sdx_shipcores` |
| Storage | 24 |  | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 0 |  | ShutOff | — | `production`, `productionBasic`, `productionAdvanced` |
| Tools | 0 |  | ShutOff | — | `Welders`, `Grinders`, `Drills` |
| Hangars | 0 |  | ShutOff | — | `hangarsCivilian`, `hangarsMilitary`, `hangarsStation` |
| Utilities | 15 |  | ShutOff | — | `Gyroscopes`, `Decoys` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalDirectional`, `sdx_sensorsOpticalFocused` |
| Small Radar | 1 |  | ShutOff | — | `sdx_sensorsRadar1x1` |
| Large Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar2x2` |
| Passive Directional Multi-band Sensor | 0 |  | ShutOff | — | `sdx_sensorsMultiDirectional` |
| Ore Detectors | 0 |  | ShutOff | — | `OreDetectors` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Corvette  (Combat, 550 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Ceramics | 40 | yes | Delete | — | `ceramics` |
| Offensive Weapons | 62 | yes | ShutOff | — | `weapons` |
| Point Defense Cannons | 8 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 28 | yes | ShutOff | — | `torpedoLaunchers` |
| Fixed Railguns | 1 | yes | ShutOff | Forward | `railgunsFixed` |
| Turreted Railguns | 0 |  | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 2 | yes | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Power Blocks | 9 | yes | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian` |
| Solar Panels | 0 | yes | ShutOff | — | `solarPanels` |
| Ship Cores | 10 | yes | ShutOff | Forward | `sdx_shipcores` |
| Storage | 40 |  | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 0 |  | ShutOff | — | `production`, `productionBasic`, `productionAdvanced` |
| Welders and Drills | 0 |  | ShutOff | — | `Welders`, `Drills` |
| Grinders | 1 |  | ShutOff | — | `Grinders` |
| Hangars | 0 |  | ShutOff | — | `hangarsCivilian`, `hangarsMilitary`, `hangarsStation` |
| Utilities | 25 | yes | ShutOff | — | `Gyroscopes`, `Decoys` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalDirectional`, `sdx_sensorsOpticalFocused` |
| Small Radar | 1 |  | ShutOff | — | `sdx_sensorsRadar1x1` |
| Large Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar2x2` |
| Passive Directional Multi-band Sensor | 0 |  | ShutOff | — | `sdx_sensorsMultiDirectional` |
| Ore Detectors | 0 |  | ShutOff | — | `OreDetectors` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Frigate  (Combat, 500 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Ceramics | 60 | yes | Delete | — | `ceramics` |
| Offensive Weapons | 90 | yes | ShutOff | — | `weapons` |
| Point Defense Cannons | 12 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 56 | yes | ShutOff | — | `torpedoLaunchers` |
| Fixed Railguns | 2 | yes | ShutOff | Forward | `railgunsFixed` |
| Turreted Railguns | 0 |  | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 4 | yes | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Power Blocks | 13 | yes | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian` |
| Solar Panels | 0 |  | ShutOff | — | `solarPanels` |
| Ship Cores | 10 | yes | ShutOff | Forward | `sdx_shipcores` |
| Storage | 75 |  | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 0 |  | ShutOff | — | `production`, `productionBasic`, `productionAdvanced` |
| Welders and Drills | 0 |  | ShutOff | — | `Welders`, `Drills` |
| Grinders | 2 |  | ShutOff | — | `Grinders` |
| Hangars | 0 |  | ShutOff | — | `hangarsCivilian`, `hangarsMilitary`, `hangarsStation` |
| Utilities | 50 | yes | ShutOff | — | `Gyroscopes`, `Decoys` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsOpticalDirectional` |
| Focused Sensors | 0 |  | ShutOff | — | `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalFocused` |
| Small Radar | 1 |  | ShutOff | — | `sdx_sensorsRadar1x1` |
| Large Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar2x2` |
| Passive Directional Multi-band Sensor | 0 |  | ShutOff | — | `sdx_sensorsMultiDirectional` |
| Ore Detectors | 0 |  | ShutOff | — | `OreDetectors` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Cruiser  (Combat, 450 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Ceramics | 120 | yes | Delete | — | `ceramics` |
| Offensive Weapons | 102 | yes | ShutOff | — | `weapons` |
| Point Defense Cannons | 26 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 70 | yes | ShutOff | — | `torpedoLaunchers` |
| Fixed Railguns | 2 | yes | ShutOff | Forward | `railgunsFixed` |
| Turreted Railguns | 1 | yes | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 8 | yes | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Power Blocks | 25 | yes | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian` |
| Solar Panels | 0 |  | ShutOff | — | `solarPanels` |
| Ship Cores | 10 | yes | ShutOff | Forward | `sdx_shipcores` |
| Storage | 155 |  | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 0 |  | ShutOff | — | `production`, `productionBasic`, `productionAdvanced` |
| Welders and Drills | 0 |  | ShutOff | — | `Welders`, `Drills` |
| Grinders | 4 |  | ShutOff | — | `Grinders` |
| Hangars | 1 |  | ShutOff | — | `hangarsCivilian` |
| Military Hangars | 0 |  | ShutOff | — | `hangarsMilitary`, `hangarsStation` |
| Utilities | 70 | yes | ShutOff | — | `Gyroscopes`, `Decoys` |
| Multi-Directional Sensors | 5 |  | ShutOff | — | `sdx_sensorsMultiDirectional` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsOpticalDirectional` |
| Small Radar | 1 |  | ShutOff | — | `sdx_sensorsRadar1x1` |
| Focused Sensors | 0 |  | ShutOff | — | `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalFocused` |
| Large Radar | 0 |  | ShutOff | — | `sdx_sensorsRadar2x2` |
| Ore Detectors | 0 |  | ShutOff | — | `OreDetectors` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Carrier  (Combat, 300 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Ceramics | 240 | yes | Delete | — | `ceramics` |
| Epstein Drives | 36 |  | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Offensive Weapons | 102 |  | ShutOff | — | `weapons` |
| Point Defense Cannons | 20 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 70 |  | ShutOff | — | `torpedoLaunchers` |
| Fixed Railguns | 2 |  | ShutOff | Forward | `railgunsFixed` |
| Turreted Railguns | 1 |  | ShutOff | — | `railgunsTurreted` |
| Power Blocks | 25 | yes | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian` |
| Solar Panels | 0 |  | ShutOff | — | `solarPanels` |
| Ship Cores | 10 | yes | ShutOff | Forward | `sdx_shipcores` |
| Storage | 750 | yes | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Production | 2 |  | ShutOff | — | `production`, `productionBasic` |
| Advanced Production | 0 |  | ShutOff | — | `productionAdvanced` |
| Welders and Drills | 0 |  | ShutOff | — | `Welders`, `Drills` |
| Grinders | 6 |  | ShutOff | — | `Grinders` |
| Military Hangars | 8 | yes | ShutOff | — | `hangarsMilitary` |
| Civilian Hangars | 0 |  | ShutOff | — | `hangarsCivilian`, `hangarsStation` |
| Utilities | 150 | yes | ShutOff | — | `Gyroscopes`, `Decoys` |
| Multi-Directional Sensors | 5 |  | ShutOff | — | `sdx_sensorsMultiDirectional` |
| Directional Sensors | 5 |  | ShutOff | Forward | `sdx_sensorsRadioDirectional`, `sdx_sensorsOpticalDirectional` |
| Radar | 1 |  | ShutOff | — | `sdx_sensorsRadar1x1`, `sdx_sensorsRadar2x2` |
| Focused Sensors | 0 |  | ShutOff | — | `sdx_sensorsRadioFocused`, `sdx_sensorsOpticalFocused` |
| Ore Detectors | 0 |  | ShutOff | — | `OreDetectors` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Outpost  (Station, 50 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Offensive Weapons | 0 |  | ShutOff | — | `weapons` |
| Point Defense Cannons | 10 | yes | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 0 |  | ShutOff | — | `torpedoLaunchers` |
| Turreted Railguns | 0 |  | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 4 |  | ShutOff | Backward | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Power Blocks | 25 | yes | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian`, `solarPanels` |
| Production | 5 |  | ShutOff | — | `production`, `productionBasic` |
| Advanced Production | 0 |  | ShutOff | — | `productionAdvanced` |
| Storage | 1000 | yes | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Welders Grinders | 6 |  | ShutOff | — | `Welders`, `Drills` |
| Drills | 0 |  | ShutOff | — | `Drills` |
| Hangars | 2 | yes | ShutOff | — | `hangarsCivilian`, `hangarsMilitary` |
| Station Hangars | 0 |  | ShutOff | — | `hangarsStation` |
| Warheads | 0 |  | Delete | — | `Warheads` |

### Installation  (Station, 50 m/s)

| category | budget | critical | punishment | directions | groups |
|---|---|---|---|---|---|
| Offensive Weapons | 0 |  | ShutOff | — | `weapons` |
| Point Defense Cannons | 20 |  | ShutOff | — | `pdcsHeavyAdvWeights` |
| Torpedo Launchers | 0 |  | ShutOff | — | `torpedoLaunchers` |
| Turreted Railguns | 2 |  | ShutOff | — | `railgunsTurreted` |
| Epstein Drives | 8 |  | ShutOff | — | `torchDrives`, `epsteinDrivesCivilian`, `epsteinDrivesIndustrial`, `epsteinDrivesMilitary` |
| Production | 20 |  | ShutOff | — | `productionBasic`, `production`, `productionAdvanced` |
| Power Blocks | 37 |  | ShutOff | — | `sdx_powerBlocksMilitary`, `powerBlocksCivilian`, `solarPanels` |
| Storage | 4000 | yes | ShutOff | — | `sdx_shipConnectors`, `sdx_cargoContainers`, `sdx_waterTanks` |
| Welders and Grinders | 12 |  | ShutOff | — | `Welders`, `Grinders` |
| Drills | 0 |  | ShutOff | — | `Drills` |
| Hangars | 12 | yes | ShutOff | — | `hangarsMilitary`, `hangarsStation` |
| Civilian Hangars | 0 |  | ShutOff | — | `hangarsCivilian` |
| Warheads | 0 |  | Delete | — | `Warheads` |

## Groups — block weights

A category's budget is spent by each block's `weight`.

### `Decoys`  (4 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Decoy | `LargeDecoy` | Decoy | Large | **2** | — | — |
| Decoy | `SmallDecoy` | Decoy | Small | **2** | — | — |
| Flat Decoy | `sdx_decoyMultiFlat` | Decoy | Large | **4** | — | — |
| Truss Decoy | `TrussPillarDecoy` | Decoy | Large | **2** | — | — |

### `Drills`  (5 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Drill | `LargeBlockDrill` | Drill | Large | **1** | — | — |
| Drill | `SmallBlockDrill` | Drill | Small | **1** | — | — |
| Drill Type II | `LargeBlockDrillReskin` | Drill | Large | **1** | — | — |
| Drill Type II | `SmallBlockDrillReskin` | Drill | Small | **1** | — | — |
| Improvised Drill | `sdx_drillImprovisedLg` | Drill | Large | **1** | — | — |

### `Grinders`  (7 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Grinder | `LargeShipGrinder` | ShipGrinder | Large | **1** | 15.625 | — |
| Grinder | `SmallShipGrinder` | ShipGrinder | Small | **1** | 3.375 | — |
| Grinder Toolcore | `sdx_grinderVanillaLg` | ConveyorSorter | Large | **1** | — | — |
| Grinder Type II | `LargeShipGrinderReskin` | ShipGrinder | Large | **1** | 15.625 | — |
| Grinder Type II | `SmallShipGrinderReskin` | ShipGrinder | Small | **1** | 3.375 | — |
| Grinder Type II Toolcore | `sdx_grinderVanillaReskinLg` | ConveyorSorter | Large | **1** | — | — |
| Improvised Grinder | `sdx_grinderImprovisedLg` | ConveyorSorter | Large | **1** | — | — |

### `Gyroscopes`  (4 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Braced Gyroscope | `sdx_gyroscopeBraced_large` | Gyro | Large | **1** | — | — |
| Gyroscope | `LargeBlockGyro` | Gyro | Large | **1** | — | — |
| Gyroscope | `SmallBlockGyro` | Gyro | Small | **1** | — | — |
| RCS Control Computer (Gyroscope) | `sdg_rcsGyroComputer` | Gyro | Large | **2** | — | — |

### `OreDetectors`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Ore Detector | `LargeOreDetector` | OreDetector | Large | **1** | — | — |
| Ore Detector Type II | `LargeOreDetectorReskin` | OreDetector | Large | **1** | — | — |

### `Warheads`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Warhead | `LargeWarhead` | Warhead | Large | **1** | — | — |
| Warhead | `SmallWarhead` | Warhead | Small | **1** | — | — |

### `Welders`  (9 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Deep Welder Toolcore | `sdx_welderVanillaDeepLg` | ConveyorSorter | Large | **1** | — | — |
| Deep Welder Type II Toolcore | `sdx_welderVanillaReskinDeepLg` | ConveyorSorter | Large | **1** | — | — |
| Improvised Welder | `sdx_welderImprovisedLg` | ConveyorSorter | Large | **1** | — | — |
| Welder | `LargeShipWelder` | ShipWelder | Large | **1** | 15.625 | — |
| Welder | `SmallShipWelder` | ShipWelder | Small | **1** | 3.375 | — |
| Welder Toolcore | `sdx_welderVanillaLg` | ConveyorSorter | Large | **1** | — | — |
| Welder Type II | `LargeShipWelderReskin` | ShipWelder | Large | **1** | 15.625 | — |
| Welder Type II | `SmallShipWelderReskin` | ShipWelder | Small | **1** | 3.375 | — |
| Welder Type II Toolcore | `sdx_welderVanillaReskinLg` | ConveyorSorter | Large | **1** | — | — |

### `ceramics`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Ceramic Armour | `sdx_armorCeramic` | CubeBlock | Large | **1** | — | — |
| Reinforced Small Cargo Container | `sdx_cargocontainerReinforced1x1` | CargoContainer | Large | **2** | 15.625 | — |

### `epsteinDrivesCivilian`  (4 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Epstein Technologies “Esquibel” Series Drive | `sdx_driveCivilian5x5` | Thrust | Large | **2** | — | 77000000.0 |
| Epstein Technologies “Manéo” Series Drive | `sdx_driveCivilian3x3_small` | Thrust | Small | **1** | — | 55000000.0 |
| Epstein Technologies “Rockhopper” Series Drive | `sdx_driveCivilian3x3` | Thrust | Large | **1** | — | 35000000.0 |
| Epstein Technologies “Solomon” Series Drive | `sdx_driveCivilian7x7` | Thrust | Large | **4** | — | 170000000.0 |

### `epsteinDrivesIndustrial`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Industrial “Canterbury” Series Drive | `sdx_driveIndustrial7x7` | Thrust | Large | **4** | — | 350000000.0 |
| Industrial “Scopuli” Series Drive | `sdx_driveIndustrial9x9` | Thrust | Large | **6** | — | 703000000.0 |

### `epsteinDrivesMilitary`  (9 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| G-1000 "Kamina" Series Drive | `sdx_driveOpaMilitary5x5` | Thrust | Large | **2** | — | 102850000.0 |
| G-2000 "Gatamang" Series Drive | `sdx_driveOpaMilitary7x7` | Thrust | Large | **4** | — | 226000000.0 |
| G-750 "Michio" Series Drive | `sdx_driveOpaMilitary3x3` | Thrust | Large | **1** | — | 46750000.0 |
| RT6-B "Morrigan" Series Drive | `sdx_driveMcrnMilitary3x3` | Thrust | Large | **1** | — | 60500000.0 |
| RT7 "Tachi" Series Drive | `sdx_driveMcrnMilitary5x5` | Thrust | Large | **2** | — | 133000000.0 |
| RTF-B "Scirocco" Series Drive | `sdx_driveMcrnMilitary7x7` | Thrust | Large | **4** | — | 292000000.0 |
| S-100 "Phantom" Series Drive | `sdx_driveUnnMilitary3x3` | Thrust | Large | **1** | — | 52250000.0 |
| S-250 "Leonidas" Series Drive | `sdx_driveUnnMilitary5x5` | Thrust | Large | **2** | — | 115000000.0 |
| S-700 "Xerxes" Series Drive | `sdx_driveUnnMilitary7x7` | Thrust | Large | **4** | — | 252000000.0 |

### `hangarsCivilian`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Civilian Hangar Pad 3x3 | `sdx_hangar3x3` | FunctionalBlock | Large | **1** | 0.0 | — |
| Civilian Hangar Pad 5x5 | `sdx_hangar5x5Civilian` | FunctionalBlock | Large | **2** | 0.0 | — |

### `hangarsMilitary`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Military Hangar Pad 5x5 | `sdx_hangar5x5Military` | FunctionalBlock | Large | **2** | 0.0 | — |
| Military Hangar Pad 7x5 | `sdx_hangar7x5` | FunctionalBlock | Large | **4** | 0.0 | — |

### `hangarsStation`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Station Hangar Pad 11x7 | `sdx_hangar11x7` | FunctionalBlock | Large | **6** | — | — |

### `pdcsAdv`  (9 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| MCRN Maegnus PDC | `sdx_pdcMcrnAdv` | ConveyorSorter | Large | **1** | — | — |
| MCRN Maegnus PDC 30° | `sdx_pdcMcrnAdvHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Maegnus PDC 45° | `sdx_pdcMcrnAdvSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC | `sdx_pdcOpaAdv` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC 30° | `sdx_pdcOpaAdvHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC 45° | `sdx_pdcOpaAdvSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC | `sdx_pdcUnnAdv` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC 30° | `sdx_pdcUnnAdvHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC 45° | `sdx_pdcUnnAdvSlope` | ConveyorSorter | Large | **1** | — | — |

### `pdcsEvenAdvWeights`  (21 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Improvised Model 17 PDC | `sdx_pdcImprovised` | ConveyorSorter | Large | **1** | — | — |
| Improvised Model 17 PDC 30° | `sdx_pdcImprovisedHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| Improvised Model 17 PDC 45° | `sdx_pdcImprovisedSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Maegnus PDC | `sdx_pdcMcrnAdv` | ConveyorSorter | Large | **1** | — | — |
| MCRN Maegnus PDC 30° | `sdx_pdcMcrnAdvHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Maegnus PDC 45° | `sdx_pdcMcrnAdvSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Nariman Dynamics PDC | `sdx_pdcMcrn` | ConveyorSorter | Large | **1** | — | — |
| MCRN Nariman Dynamics PDC 30° | `sdx_pdcMcrnHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Nariman Dynamics PDC 45° | `sdx_pdcMcrnSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC | `sdx_pdcOpaAdv` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC 30° | `sdx_pdcOpaAdvHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC 45° | `sdx_pdcOpaAdvSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Kess-Hashari PDC | `sdx_pdcOpa` | ConveyorSorter | Large | **1** | — | — |
| OPA Kess-Hashari PDC 30° | `sdx_pdcOpaHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Kess-Hashari PDC 45° | `sdx_pdcOpaSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Mikazuki Munitions PDC | `sdx_pdcUnn` | ConveyorSorter | Large | **1** | — | — |
| UNN Mikazuki Munitions PDC 30° | `sdx_pdcUnnHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Mikazuki Munitions PDC 45° | `sdx_pdcUnnSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC | `sdx_pdcUnnAdv` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC 30° | `sdx_pdcUnnAdvHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC 45° | `sdx_pdcUnnAdvSlope` | ConveyorSorter | Large | **1** | — | — |

### `pdcsHeavyAdvWeights`  (21 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Improvised Model 17 PDC | `sdx_pdcImprovised` | ConveyorSorter | Large | **1** | — | — |
| Improvised Model 17 PDC 30° | `sdx_pdcImprovisedHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| Improvised Model 17 PDC 45° | `sdx_pdcImprovisedSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Maegnus PDC | `sdx_pdcMcrnAdv` | ConveyorSorter | Large | **2** | — | — |
| MCRN Maegnus PDC 30° | `sdx_pdcMcrnAdvHalfSlope` | ConveyorSorter | Large | **2** | — | — |
| MCRN Maegnus PDC 45° | `sdx_pdcMcrnAdvSlope` | ConveyorSorter | Large | **2** | — | — |
| MCRN Nariman Dynamics PDC | `sdx_pdcMcrn` | ConveyorSorter | Large | **1** | — | — |
| MCRN Nariman Dynamics PDC 30° | `sdx_pdcMcrnHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| MCRN Nariman Dynamics PDC 45° | `sdx_pdcMcrnSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Fragmanta PDC | `sdx_pdcOpaAdv` | ConveyorSorter | Large | **2** | — | — |
| OPA Fragmanta PDC 30° | `sdx_pdcOpaAdvHalfSlope` | ConveyorSorter | Large | **2** | — | — |
| OPA Fragmanta PDC 45° | `sdx_pdcOpaAdvSlope` | ConveyorSorter | Large | **2** | — | — |
| OPA Kess-Hashari PDC | `sdx_pdcOpa` | ConveyorSorter | Large | **1** | — | — |
| OPA Kess-Hashari PDC 30° | `sdx_pdcOpaHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| OPA Kess-Hashari PDC 45° | `sdx_pdcOpaSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Mikazuki Munitions PDC | `sdx_pdcUnn` | ConveyorSorter | Large | **1** | — | — |
| UNN Mikazuki Munitions PDC 30° | `sdx_pdcUnnHalfSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Mikazuki Munitions PDC 45° | `sdx_pdcUnnSlope` | ConveyorSorter | Large | **1** | — | — |
| UNN Redfield Ballistics PDC | `sdx_pdcUnnAdv` | ConveyorSorter | Large | **2** | — | — |
| UNN Redfield Ballistics PDC 30° | `sdx_pdcUnnAdvHalfSlope` | ConveyorSorter | Large | **2** | — | — |
| UNN Redfield Ballistics PDC 45° | `sdx_pdcUnnAdvSlope` | ConveyorSorter | Large | **2** | — | — |

### `powerBlocksCivilian`  (13 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Battery | `LargeBlockBatteryBlock` | BatteryBlock | Large | **1** | — | — |
| Battery Bank | `LargeBlockBatteryReskin` | BatteryBlock | Large | **1** | — | — |
| Battery Bank | `SmallBlockBatteryReskin` | BatteryBlock | Small | **1** | — | — |
| Battery Bank Offset | `LargeBlockBatteryReskinOffset` | BatteryBlock | Large | **1** | — | — |
| Civilian Fusion Reactor | `LargeBlockLargeGenerator` | Reactor | Large | **6** | — | — |
| Civilian Fusion Reactor | `LargeBlockSmallGenerator` | Reactor | Large | **2** | — | — |
| Civilian Fusion Reactor | `SmallBlockLargeGenerator` | Reactor | Small | **3** | — | — |
| Civilian Fusion Reactor | `SmallBlockSmallGenerator` | Reactor | Small | **1** | — | — |
| Civilian Warfare Fusion Reactor | `LargeBlockLargeGeneratorWarfare2` | Reactor | Large | **6** | — | — |
| Civilian Warfare Fusion Reactor | `LargeBlockSmallGeneratorWarfare2` | Reactor | Large | **2** | — | — |
| Civilian Warfare Fusion Reactor | `SmallBlockLargeGeneratorWarfare2` | Reactor | Small | **3** | — | — |
| Civilian Warfare Fusion Reactor | `SmallBlockSmallGeneratorWarfare2` | Reactor | Small | **1** | — | — |
| Warfare Battery | `LargeBlockBatteryBlockWarfare2` | BatteryBlock | Large | **1** | — | — |

### `production`  (6 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Assembler | `LargeAssembler` | Assembler | Large | **1** | — | — |
| Industrial Assembler | `LargeAssemblerIndustrial` | Assembler | Large | **1** | — | — |
| Industrial Refinery | `LargeRefineryIndustrial` | Refinery | Large | **1** | — | — |
| Lab O2/H20 Generator | `LargeBlockOxygenGeneratorLab` | OxygenGenerator | Large | **1** | — | — |
| O2/H20 Generator | `` | OxygenGenerator | Large | **1** | — | — |
| Refinery | `LargeRefinery` | Refinery | Large | **1** | — | — |

### `productionAdvanced`  (7 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Advanced O2/H20 Generator | `sdx_productionO2GeneratorLG` | OxygenGenerator | Large | **1** | — | — |
| Arc Furnace | `sdx_productionArcFurnace` | Refinery | Large | **1** | — | — |
| Blast Forge Production | `sdx_productionBlastForge` | Assembler | Large | **1** | — | — |
| Fusion Hardware Fabricator | `sdx_productionFusionHardwareFabricator` | Assembler | Large | **1** | — | — |
| Munitions Plant | `sdx_productionMunitionsPlant` | Assembler | Large | **1** | — | — |
| Research Lab | `sdx_productionResearchLab` | Assembler | Large | **1** | — | — |
| Research Lab Advanced | `sdx_productionResearchLabAdvanced` | Assembler | Large | **1** | — | — |

### `productionBasic`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Basic Assembler | `BasicAssembler` | Assembler | Large | **1** | — | — |
| Basic Refinery | `Blast Furnace` | Refinery | Large | **1** | — | — |

### `productionWater`  (5 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Advanced O2/H20 Generator | `sdx_productionO2GeneratorLG` | OxygenGenerator | Large | **1** | — | — |
| Lab O2/H20 Generator | `LargeBlockOxygenGeneratorLab` | OxygenGenerator | Large | **1** | — | — |
| Lab O2/H20 Generator | `SmallBlockOxygenGeneratorLab` | OxygenGenerator | Small | **1** | — | — |
| O2/H20 Generator | `` | OxygenGenerator | Large | **1** | — | — |
| O2/H20 Generator | `OxygenGeneratorSmall` | OxygenGenerator | Small | **1** | — | — |

### `railgunsFixed`  (4 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Improvised Model 7000 Fixed Coilgun | `sdx_railgunImprovisedLightFixed` | ConveyorSorter | Large | **1** | — | — |
| MCRN Dagger Railgun | `sdx_railgunMcrnMediumFixed` | ConveyorSorter | Large | **1** | — | — |
| OPA Malisetara Railgun | `sdx_railgunOpaMediumFixed` | ConveyorSorter | Large | **1** | — | — |
| UNN Munroe Railgun | `sdx_railgunUnnLightFixed` | ConveyorSorter | Large | **1** | — | — |

### `railgunsTurreted`  (4 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Improvised MM-30 Coilgun | `sdx_railgunImprovisedLightTurreted` | ConveyorSorter | Large | **1** | — | — |
| MCRN V-14 Stilleto Railgun | `sdx_railgunMcrnMediumTurreted` | ConveyorSorter | Large | **1** | — | — |
| OPA Ashford Railgun | `sdx_railgunOpaLightTurreted` | ConveyorSorter | Large | **1** | — | — |
| UNN Dawson-Pattern Railgun | `sdx_railgunUnnMediumTurreted` | ConveyorSorter | Large | **1** | — | — |

### `sdx_cargoContainers`  (18 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| 3x11x3 Cargo Container | `3x11x3LargeContainer` | CargoContainer | Large | **40** | 1546.875 | — |
| 3x3x1 Cargo Container | `3x3x1Cargo` | CargoContainer | Large | **9** | 140.625 | — |
| 3x3x1 Open Cargo Container | `3x3x1OpenCargo` | CargoContainer | Large | **9** | 140.625 | — |
| 3x3x1 Open Cargo No Floor | `3x3x1OpenCargoV2` | CargoContainer | Large | **9** | 140.625 | — |
| 3x5x3 Cargo Container | `3x5x3LargeContainer` | CargoContainer | Large | **35** | 703.125 | — |
| 7x11x3 Cargo Container | `7x11x3LargeContainer` | CargoContainer | Large | **45** | 3609.375 | — |
| Bulk Cargo Container A | `LargeBlockBulkContainerA` | CargoContainer | Large | **35** | 820.0 | — |
| Bulk Cargo Container B | `LargeBlockBulkContainerB` | CargoContainer | Large | **35** | 820.0 | — |
| Bulk Cargo Container C | `LargeBlockBulkContainerC` | CargoContainer | Large | **35** | 820.0 | — |
| Cargo Access Tube | `EDPAccessCargoTube` | CargoContainer | Large | **0.5** | 8.099999 | — |
| Cargo Terminal | `LargeBlockCargoTerminal` | CargoContainer | Large | **1** | 15.625 | — |
| Cargo Terminal Half | `LargeBlockCargoTerminalHalf` | CargoContainer | Large | **0.5** | 7.5 | — |
| Half Block Cargo | `HalfBlockCargo` | CargoContainer | Large | **0.5** | 7.8125 | — |
| Large Cargo Container | `LargeBlockLargeContainer` | CargoContainer | Large | **25** | 421.875 | — |
| Large Freight Cargo Container 7x7x7 | `sdx_cargocontainer7x7x7` | CargoContainer | Large | **50** | 6591.797 | — |
| Large Freight Cargo Container 7x7x9 | `sdx_cargocontainer7x7x9` | CargoContainer | Large | **50** | 7910.1562 | — |
| Large Industrial Cargo Container | `LargeBlockLargeIndustrialContainer` | CargoContainer | Large | **25** | 421.875 | — |
| Small Cargo Container | `LargeBlockSmallContainer` | CargoContainer | Large | **1** | 15.625 | — |

### `sdx_powerBlocksMilitary`  (3 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Extra Small Military Fusion Reactor | `sdx_reactorFusion1x1` | Reactor | Large | **2** | — | — |
| Medium Military Fusion Reactor | `sdx_reactorFusion5x5` | Reactor | Large | **12** | — | — |
| Small Military Fusion Reactor | `sdx_reactorFusion3x3` | Reactor | Large | **6** | — | — |

### `sdx_sensorsMultiDirectional`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Sensor Panel | `sdx_detectorPassiveMultiDirectional` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsMultiOmni`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Sensor Array | `sdx_detectorPassiveMultiOmnidirectional` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsOpticalDirectional`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Optical Scope | `sdx_detectorPassiveOpticalDirectional` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsOpticalFocused`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Advanced Optical Dish | `sdx_detectorPassiveOpticalFocused` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsRadar1x1`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Radar | `sdx_detectorActiveRadioOmnidirectional_1x1` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsRadar2x2`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Large Radar | `sdx_detectorActiveRadioOmnidirectional_2x2` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsRadioDirectional`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Radio Dish | `sdx_detectorPassiveRadioDirectional` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsRadioFocused`  (1 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Advanced Radio Detector | `sdx_detectorPassiveRadioFocused` | FunctionalBlock | Large | **1** | — | — |

### `sdx_sensorsRadioOmni`  (2 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Radio Detector | `sdx_detectorPassiveRadioOmnidirectional` | FunctionalBlock | Large | **0** | — | — |
| Radio Detector Mast | `sdx_detectorPassiveRadioOmnidirectional2` | FunctionalBlock | Large | **0** | — | — |

### `sdx_shipConnectors`  (11 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Connector | `Connector` | ShipConnector | Large | **1** | — | — |
| Connector | `ConnectorMedium` | ShipConnector | Small | **1** | — | — |
| Inset Connector | `LargeBlockInsetConnector` | ShipConnector | Large | **1** | — | — |
| Inset Connector | `SmallBlockInsetConnectorMedium` | ShipConnector | Small | **1** | — | — |
| Large Docking Connector | `sdx_connectorDockingLarge1` | ShipConnector | Large | **1** | 15.625 | — |
| Large Docking Connector Half | `sdx_connectorDockingLargeHalf1` | ShipConnector | Large | **1** | 15.625 | — |
| Small Connector | `ConnectorSmall` | ShipConnector | Small | **1** | — | — |
| Small Inset Connector | `LargeBlockInsetConnectorSmall` | ShipConnector | Large | **1** | — | — |
| Small Inset Connector | `SmallBlockInsetConnector` | ShipConnector | Small | **1** | — | — |
| Station Large Docking Connector | `sdx_connectorDockingLargeStation1` | ShipConnector | Large | **1** | 15.625 | — |
| Structural Platform Connector | `LargeBlockStructural_PlatformConnector` | ShipConnector | Large | **1** | 8.0 | — |

### `sdx_shipcores`  (7 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Barge Shipcore | `sdx_shipcoreBarge` | FunctionalBlock | Large | **1** | — | — |
| Carrier Shipcore | `sdx_shipcoreCarrier` | FunctionalBlock | Large | **1** | — | — |
| Corvette Shipcore | `sdx_shipcoreCorvette` | FunctionalBlock | Large | **1** | — | — |
| Cruiser Shipcore | `sdx_shipcoreCruiser` | FunctionalBlock | Large | **1** | — | — |
| Frigate Shipcore | `sdx_shipcoreFrigate` | FunctionalBlock | Large | **1** | — | — |
| Hauler Shipcore | `sdx_shipcoreHauler` | FunctionalBlock | Large | **1** | — | — |
| Picket Shipcore | `sdx_shipcorePicket` | FunctionalBlock | Large | **1** | — | — |

### `sdx_waterTanks`  (11 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| 5x5 Water Tank (End) | `sdx_tankWaterEnd5x5_large` | OxygenTank | Large | **30** | 600000.0 | — |
| 5x5 Water Tank (Middle) | `sdx_tankWaterMiddle5x5_large` | OxygenTank | Large | **45** | 1000000.0 | — |
| Canterbury Water Tank | `sdx_tankWater7x19` | OxygenTank | Large | **125** | 7000000.0 | — |
| Industrial Large Water Tank | `LargeHydrogenTankIndustrial` | OxygenTank | Large | **25** | 270000.0 | — |
| Lab Small Water Tank | `LargeHydrogenTankSmallLab` | OxygenTank | Large | **5** | 30000.0 | — |
| Lab Water Tank | `SmallHydrogenTankLab` | OxygenTank | Small | **15** | 5000.0 | — |
| Large 2x3 Water Tank | `sdx_tankWater2x3_large` | OxygenTank | Large | **15** | 125000.0 | — |
| Large Water Tank | `LargeHydrogenTank` | OxygenTank | Large | **25** | 270000.0 | — |
| Large Water Tank | `SmallHydrogenTank` | OxygenTank | Small | **15** | 5000.0 | — |
| Small Water Tank | `LargeHydrogenTankSmall` | OxygenTank | Large | **5** | 30000.0 | — |
| Small Water Tank | `SmallHydrogenTankSmall` | OxygenTank | Small | **5** | 1000.0 | — |

### `solarPanels`  (4 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Colorable Solar Panel | `LargeBlockColorableSolarPanel` | SolarPanel | Large | **1** | — | — |
| Colorable Solar Panel Slope Left | `LargeBlockColorableSolarPanelCorner` | SolarPanel | Large | **1** | — | — |
| Colorable Solar Panel Slope Right | `LargeBlockColorableSolarPanelCornerInverted` | SolarPanel | Large | **1** | — | — |
| Solar Panel | `LargeBlockSolarPanel` | SolarPanel | Large | **1** | — | — |

### `torchDrives`  (13 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Industrial Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrustIndustrial` | Thrust | Large | **0.5** | — | 10000000.0 |
| Industrial Large Fusion Torch Drive | `SmallBlockLargeHydrogenThrustIndustrial` | Thrust | Small | **0.5** | — | 480000.0 |
| Industrial Large Fusion Torch Drive | `SmallBlockSmallHydrogenThrustIndustrial` | Thrust | Small | **0.25** | — | 98400.0 |
| Industrial Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrustIndustrial` | Thrust | Large | **0.25** | — | 3000000.0 |
| Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrust` | Thrust | Large | **0.5** | — | 10000000.0 |
| Large Fusion Torch Drive | `SmallBlockLargeHydrogenThrust` | Thrust | Small | **0.5** | — | 480000.0 |
| Large Fusion Torch Drive | `SmallBlockSmallHydrogenThrust` | Thrust | Small | **0.25** | — | 98400.0 |
| Sci-fi Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrustReskin` | Thrust | Large | **0.5** | — | 10000000.0 |
| Sci-fi Large Fusion Torch Drive | `SmallBlockLargeHydrogenThrustReskin` | Thrust | Small | **0.5** | — | 480000.0 |
| Sci-fi Large Fusion Torch Drive | `SmallBlockSmallHydrogenThrustReskin` | Thrust | Small | **0.25** | — | 98400.0 |
| Sci-fi Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrustReskin` | Thrust | Large | **0.25** | — | 3000000.0 |
| Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrust` | Thrust | Large | **0.25** | — | 3000000.0 |
| Small Fusion Torch Drive | `sdx_driveTorch3x3_small` | Thrust | Small | **0.5** | — | 55000000.0 |

### `torpedoLaunchers`  (9 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Ares 220mm Torpedo Launcher | `sdx_torpedoLauncherMediumTriple` | ConveyorSorter | Large | **10** | — | — |
| Artemis 220mm Torpedo Launcher | `sdx_torpedoLauncherMediumSingle` | ConveyorSorter | Large | **4** | — | — |
| Artemis 220mm Torpedo Launcher Half Slope | `sdx_torpedoLauncherMediumSingleHalfSlope` | ConveyorSorter | Large | **4** | — | — |
| Athena 220mm Torpedo Launcher | `sdx_torpedoLauncherMediumDouble` | ConveyorSorter | Large | **7** | — | — |
| Hachiman 160mm Torpedo Launcher | `sdx_torpedoLauncherLightTriple` | ConveyorSorter | Large | **10** | — | — |
| Improvised Double Torpedo Launcher | `sdx_torpedoLauncherImprovisedDouble` | ConveyorSorter | Large | **7** | — | — |
| Omoikane 160mm Torpedo Launcher | `sdx_torpedoLauncherLightSingle` | ConveyorSorter | Large | **4** | — | — |
| Omoikane 160mm Torpedo Launcher Half Slope | `sdx_torpedoLauncherLightSingleHalfSlope` | ConveyorSorter | Large | **4** | — | — |
| Raijin 160mm Torpedo Launcher | `sdx_torpedoLauncherLightDouble` | ConveyorSorter | Large | **7** | — | — |

### `weapons`  (41 blocks)

| block | subtype | type | size | weight | capacity | thrust |
|---|---|---|---|---|---|---|
| Advanced Optical Dish | `sdx_detectorPassiveOpticalFocused` | FunctionalBlock | Large | **42** | — | — |
| Advanced Radio Detector | `sdx_detectorPassiveRadioFocused` | FunctionalBlock | Large | **42** | — | — |
| Ares 220mm Torpedo Launcher | `sdx_torpedoLauncherMediumTriple` | ConveyorSorter | Large | **10** | — | — |
| Artemis 220mm Torpedo Launcher | `sdx_torpedoLauncherMediumSingle` | ConveyorSorter | Large | **4** | — | — |
| Artemis 220mm Torpedo Launcher Half Slope | `sdx_torpedoLauncherMediumSingleHalfSlope` | ConveyorSorter | Large | **4** | — | — |
| Athena 220mm Torpedo Launcher | `sdx_torpedoLauncherMediumDouble` | ConveyorSorter | Large | **7** | — | — |
| Hachiman 160mm Torpedo Launcher | `sdx_torpedoLauncherLightTriple` | ConveyorSorter | Large | **10** | — | — |
| Improvised Double Torpedo Launcher | `sdx_torpedoLauncherImprovisedDouble` | ConveyorSorter | Large | **7** | — | — |
| Improvised MM-30 Coilgun | `sdx_railgunImprovisedLightTurreted` | ConveyorSorter | Large | **42** | — | — |
| Improvised Model 17 PDC | `sdx_pdcImprovised` | ConveyorSorter | Large | **0** | — | — |
| Improvised Model 17 PDC 30° | `sdx_pdcImprovisedHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| Improvised Model 17 PDC 45° | `sdx_pdcImprovisedSlope` | ConveyorSorter | Large | **0** | — | — |
| Improvised Model 7000 Fixed Coilgun | `sdx_railgunImprovisedLightFixed` | ConveyorSorter | Large | **34** | — | — |
| Large Radar | `sdx_detectorActiveRadioOmnidirectional_2x2` | FunctionalBlock | Large | **7** | — | — |
| MCRN Dagger Railgun | `sdx_railgunMcrnMediumFixed` | ConveyorSorter | Large | **34** | — | — |
| MCRN Maegnus PDC | `sdx_pdcMcrnAdv` | ConveyorSorter | Large | **0** | — | — |
| MCRN Maegnus PDC 30° | `sdx_pdcMcrnAdvHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| MCRN Maegnus PDC 45° | `sdx_pdcMcrnAdvSlope` | ConveyorSorter | Large | **0** | — | — |
| MCRN Nariman Dynamics PDC | `sdx_pdcMcrn` | ConveyorSorter | Large | **0** | — | — |
| MCRN Nariman Dynamics PDC 30° | `sdx_pdcMcrnHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| MCRN Nariman Dynamics PDC 45° | `sdx_pdcMcrnSlope` | ConveyorSorter | Large | **0** | — | — |
| MCRN V-14 Stilleto Railgun | `sdx_railgunMcrnMediumTurreted` | ConveyorSorter | Large | **42** | — | — |
| OPA Ashford Railgun | `sdx_railgunOpaLightTurreted` | ConveyorSorter | Large | **42** | — | — |
| OPA Fragmanta PDC | `sdx_pdcOpaAdv` | ConveyorSorter | Large | **0** | — | — |
| OPA Fragmanta PDC 30° | `sdx_pdcOpaAdvHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| OPA Fragmanta PDC 45° | `sdx_pdcOpaAdvSlope` | ConveyorSorter | Large | **0** | — | — |
| OPA Kess-Hashari PDC | `sdx_pdcOpa` | ConveyorSorter | Large | **0** | — | — |
| OPA Kess-Hashari PDC 30° | `sdx_pdcOpaHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| OPA Kess-Hashari PDC 45° | `sdx_pdcOpaSlope` | ConveyorSorter | Large | **0** | — | — |
| OPA Malisetara Railgun | `sdx_railgunOpaMediumFixed` | ConveyorSorter | Large | **34** | — | — |
| Omoikane 160mm Torpedo Launcher | `sdx_torpedoLauncherLightSingle` | ConveyorSorter | Large | **4** | — | — |
| Omoikane 160mm Torpedo Launcher Half Slope | `sdx_torpedoLauncherLightSingleHalfSlope` | ConveyorSorter | Large | **4** | — | — |
| Raijin 160mm Torpedo Launcher | `sdx_torpedoLauncherLightDouble` | ConveyorSorter | Large | **7** | — | — |
| UNN Dawson-Pattern Railgun | `sdx_railgunUnnMediumTurreted` | ConveyorSorter | Large | **42** | — | — |
| UNN Mikazuki Munitions PDC | `sdx_pdcUnn` | ConveyorSorter | Large | **0** | — | — |
| UNN Mikazuki Munitions PDC 30° | `sdx_pdcUnnHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| UNN Mikazuki Munitions PDC 45° | `sdx_pdcUnnSlope` | ConveyorSorter | Large | **0** | — | — |
| UNN Munroe Railgun | `sdx_railgunUnnLightFixed` | ConveyorSorter | Large | **34** | — | — |
| UNN Redfield Ballistics PDC | `sdx_pdcUnnAdv` | ConveyorSorter | Large | **0** | — | — |
| UNN Redfield Ballistics PDC 30° | `sdx_pdcUnnAdvHalfSlope` | ConveyorSorter | Large | **0** | — | — |
| UNN Redfield Ballistics PDC 45° | `sdx_pdcUnnAdvSlope` | ConveyorSorter | Large | **0** | — | — |

## Thrusters

| thruster | subtype | grid | group | force N | mass kg | inf min/max | eff min/max | fuel | draw lo/hi |
|---|---|---|---|---|---|---|---|---|---|
| Industrial “Scopuli” Series | `sdx_driveIndustrial9x9` | Large | Epstein | 703,000,000 | 103,140 | 0.0/1.0 | 1.0/0.3 | Water | 29/96 |
| Industrial “Canterbury” Series | `sdx_driveIndustrial7x7` | Large | Epstein | 350,000,000 | 83,615 | 0.0/1.0 | 1.0/0.3 | Water | 17/56 |
| RTF-B "Scirocco" Series | `sdx_driveMcrnMilitary7x7` | Large | Epstein | 292,000,000 | 136,665 | 0.0/1.0 | 1.0/0.3 | Water | 11/36 |
| S-700 "Xerxes" Series | `sdx_driveUnnMilitary7x7` | Large | Epstein | 252,000,000 | 150,278 | 0.0/1.0 | 1.0/0.3 | Water | 12/41 |
| G-2000 "Gatamang" Series | `sdx_driveOpaMilitary7x7` | Large | Epstein | 226,000,000 | 143,035 | 0.0/1.0 | 1.0/0.3 | Water | 10/32 |
| Epstein Technologies “Solomon” Series | `sdx_driveCivilian7x7` | Large | Epstein | 170,000,000 | 76,449 | 0.0/1.0 | 1.0/0.3 | Water | 11/38 |
| RT7 "Tachi" Series | `sdx_driveMcrnMilitary5x5` | Large | Epstein | 133,000,000 | 55,016 | 0.0/1.0 | 1.0/0.3 | Water | 6/20 |
| S-250 "Leonidas" Series | `sdx_driveUnnMilitary5x5` | Large | Epstein | 115,000,000 | 60,885 | 0.0/1.0 | 1.0/0.3 | Water | 7/22 |
| G-1000 "Kamina" Series | `sdx_driveOpaMilitary5x5` | Large | Epstein | 102,850,000 | 57,705 | 0.0/1.0 | 1.0/0.3 | Water | 5/18 |
| Epstein Technologies “Esquibel” Series | `sdx_driveCivilian5x5` | Large | Epstein | 77,000,000 | 31,320 | 0.0/1.0 | 1.0/0.3 | Water | 5/17 |
| RT6-B "Morrigan" Series | `sdx_driveMcrnMilitary3x3` | Large | Epstein | 60,500,000 | 27,720 | 0.0/1.0 | 1.0/0.3 | Water | 3/11 |
| Small Fusion Torch | `sdx_driveTorch3x3_small` | Small | Epstein | 55,000,000 | 5,690 | 0.0/1.0 | 1.0/0.3 | Water | 1/5 |
| S-100 "Phantom" Series | `sdx_driveUnnMilitary3x3` | Large | Epstein | 52,250,000 | 30,215 | 0.0/1.0 | 1.0/0.3 | Water | 4/12 |
| G-750 "Michio" Series | `sdx_driveOpaMilitary3x3` | Large | Epstein | 46,750,000 | 29,000 | 0.0/1.0 | 1.0/0.3 | Water | 3/10 |
| Epstein Technologies “Rockhopper” Series | `sdx_driveCivilian3x3` | Large | Epstein | 35,000,000 | 12,330 | 0.0/1.0 | 1.0/0.3 | Water | 2/8 |
| Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrust` | Large | Hydrogen | 10,000,000 | 6,940 | 0.0/1.0 | 1.0/1.0 | Water | 3/3 |
| Large Atmospheric Thruster | `LargeBlockLargeAtmosphericThrust` | Large | Atmospheric | 6,480,000 | 32,970 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/16,800,000 |
| Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrust` | Large | Hydrogen | 3,000,000 | 1,420 | 0.0/1.0 | 1.0/1.0 | Water | 1/1 |
| Large Flat Atmospheric Thruster | `LargeBlockLargeFlatAtmosphericThrust` | Large | Atmospheric | 2,600,000 | 12,190 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/6,700,000 |
| S-3X RCS thruster (1x1) | `sdx_thrusterRCSBareSG` | Small | Epstein | 1,500,000 | 1,420 | 0.0/1.0 | 1.0/0.2 | Water | 0/1 |
| S-3X RCS thruster (1x1) | `sdx_thrusterRCSBareLG` | Large | Epstein | 1,500,000 | 1,420 | 0.0/1.0 | 1.0/0.2 | Water | 0/1 |
| Atmospheric Thruster | `LargeBlockSmallAtmosphericThrust` | Large | Atmospheric | 648,000 | 4,000 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/2,400,000 |
| Large Atmospheric Thruster | `SmallBlockLargeAtmosphericThrust` | Small | Atmospheric | 576,000 | 2,948 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/2,400,000 |
| Large Fusion Torch Drive | `SmallBlockLargeHydrogenThrust` | Small | Hydrogen | 480,000 | 1,222 | 0.0/1.0 | 1.0/1.0 | Water | 641/641 |
| Large Flat Atmospheric Thruster | `SmallBlockLargeFlatAtmosphericThrust` | Small | Atmospheric | 230,000 | 1,060 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/1,000,000 |
| Flat Atmospheric Thruster | `LargeBlockSmallFlatAtmosphericThrust` | Large | Atmospheric | 200,000 | 1,273 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/800,000 |
| Large Fusion Torch Drive | `SmallBlockSmallHydrogenThrust` | Small | Hydrogen | 98,400 | 334 | 0.0/1.0 | 1.0/1.0 | Water | 641/641 |
| Atmospheric Thruster | `SmallBlockSmallAtmosphericThrust` | Small | Atmospheric | 96,000 | 699 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/600,000 |
| Flat Atmospheric Thruster | `SmallBlockSmallFlatAtmosphericThrust` | Small | Atmospheric | 32,000 | 303 | 0.3/1.0 | 0.0/1.0 | Electricity | 0/200,000 |

### Thruster groups

| group | atmosphere behaviour |
|---|---|
| Atmospheric | 0% in space → 100% in atmosphere |
| Hydrogen | flat everywhere |
| Epstein | 100% in space → 20%-30% in atmosphere |

## Spectrum emitters / detectors

| block | subtype | band | trigger | tag | directional | angle° | maxStrength | gain |
|---|---|---|---|---|---|---|---|---|
| Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrust` | Optical | ScaleWithThrust | drive | True | 7.0 | 2,000,000,000 | 2.0 |
| Industrial Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrustIndustrial` | Optical | ScaleWithThrust | drive | True | 7.0 | 2,000,000,000 | 2.0 |
| Sci-fi Large Fusion Torch Drive | `LargeBlockLargeHydrogenThrustReskin` | Optical | ScaleWithThrust | drive | True | 7.0 | 2,000,000,000 | 2.0 |
| Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrust` | Optical | ScaleWithThrust | drive | True | 5.0 | 1,000,000,000 | 3.0 |
| Industrial Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrustIndustrial` | Optical | ScaleWithThrust | drive | True | 5.0 | 1,000,000,000 | 3.0 |
| Sci-fi Small Fusion Torch Drive | `LargeBlockSmallHydrogenThrustReskin` | Optical | ScaleWithThrust | drive | True | 5.0 | 1,000,000,000 | 3.0 |
| Epstein Technologies “Rockhopper” Series Drive | `sdx_driveCivilian3x3` | Optical | ScaleWithThrust | drive | True | 3.0 | 3,000,000,000 | 4.0 |
| Epstein Technologies “Esquibel” Series Drive | `sdx_driveCivilian5x5` | Optical | ScaleWithThrust | drive | True | 3.0 | 6,000,000,000 | 4.0 |
| Epstein Technologies “Solomon” Series Drive | `sdx_driveCivilian7x7` | Optical | ScaleWithThrust | drive | True | 3.0 | 12,000,000,000 | 4.0 |
| Industrial “Canterbury” Series Drive | `sdx_driveIndustrial7x7` | Optical | ScaleWithThrust | drive | True | 3.0 | 12,000,000,000 | 4.0 |
| Industrial “Scopuli” Series Drive | `sdx_driveIndustrial9x9` | Optical | ScaleWithThrust | drive | True | 3.0 | 18,000,000,000 | 4.0 |
| RT6-B "Morrigan" Series Drive | `sdx_driveMcrnMilitary3x3` | Optical | ScaleWithThrust | drive | True | 3.0 | 3,000,000,000 | 4.0 |
| RT7 "Tachi" Series Drive | `sdx_driveMcrnMilitary5x5` | Optical | ScaleWithThrust | drive | True | 3.0 | 6,000,000,000 | 4.0 |
| RTF-B "Scirocco" Series Drive | `sdx_driveMcrnMilitary7x7` | Optical | ScaleWithThrust | drive | True | 3.0 | 12,000,000,000 | 4.0 |
| G-750 "Michio" Series Drive | `sdx_driveOpaMilitary3x3` | Optical | ScaleWithThrust | drive | True | 3.0 | 3,000,000,000 | 4.0 |
| G-1000 "Kamina" Series Drive | `sdx_driveOpaMilitary5x5` | Optical | ScaleWithThrust | drive | True | 3.0 | 6,000,000,000 | 4.0 |
| G-2000 "Gatamang" Series Drive | `sdx_driveOpaMilitary7x7` | Optical | ScaleWithThrust | drive | True | 3.0 | 12,000,000,000 | 4.0 |
| S-100 "Phantom" Series Drive | `sdx_driveUnnMilitary3x3` | Optical | ScaleWithThrust | drive | True | 3.0 | 3,000,000,000 | 4.0 |
| S-250 "Leonidas" Series Drive | `sdx_driveUnnMilitary5x5` | Optical | ScaleWithThrust | drive | True | 3.0 | 6,000,000,000 | 4.0 |
| S-700 "Xerxes" Series Drive | `sdx_driveUnnMilitary7x7` | Optical | ScaleWithThrust | drive | True | 3.0 | 12,000,000,000 | 4.0 |

### Detectors

| block | detector |
|---|---|
| Radar | `{"type": "Active", "band": "Radio", "threshold": 0.1, "directional": false}` |
| Large Radar | `{"type": "Active", "band": "Radio", "threshold": 0.1, "directional": false}` |
| Sensor Panel | `{"type": "Passive", "band": "All", "threshold": 0.05, "directional": true}` |
| Sensor Array | `{"type": "Passive", "band": "All", "threshold": 0.1, "directional": false}` |
| Optical Scope | `{"type": "Passive", "band": "Optical", "threshold": 0.05, "directional": true}` |
| Advanced Optical Dish | `{"type": "Passive", "band": "Optical", "threshold": 0.025, "directional": true}` |
| Radio Dish | `{"type": "Passive", "band": "Radio", "threshold": 0.05, "directional": true}` |
| Advanced Radio Detector | `{"type": "Passive", "band": "Radio", "threshold": 0.025, "directional": true}` |
| Radio Detector | `{"type": "Passive", "band": "Radio", "threshold": 0.1, "directional": false}` |
| Radio Detector Mast | `{"type": "Passive", "band": "Radio", "threshold": 0.1, "directional": false}` |
| Lidar | `{"type": "Targeted", "band": "Optical", "threshold": 0.1, "directional": false}` |

## Gas tanks

| tank | subtype | grid | capacity | gas |
|---|---|---|---|---|
| Canterbury Water Tank | `sdx_tankWater7x19` | Large | 7,000,000 | Water |
| Large Oxygen Tank | `sdx_tankOxygen3x3` | Large | 1,000,000 | Oxygen |
| 5x5 Water Tank (Middle) | `sdx_tankWaterMiddle5x5_large` | Large | 1,000,000 | Water |
| 5x5 Water Tank (End) | `sdx_tankWaterEnd5x5_large` | Large | 600,000 | Water |
| Large Water Tank | `SmallHydrogenTankBulk` | Small | 500,000 | Water |
| Large Water Tank | `LargeHydrogenTank` | Large | 270,000 | Water |
| Large 2x3 Water Tank | `sdx_tankWater2x3_large` | Large | 125,000 | Water |
| Small Oxygen Tank | `` | Large | 100,000 | Oxygen |
| Oxygen Tank | `OxygenTankSmall` | Small | 50,000 | Oxygen |
| Small Water Tank | `LargeHydrogenTankSmall` | Large | 30,000 | Water |
| Lab Water Tank | `SmallHydrogenTankLab` | Small | 5,000 | Water |
| Small Oxygen Tank | `SmallOxygenTankSmall` | Small | 3,000 | Oxygen |
| Small Water Tank | `SmallHydrogenTankSmall` | Small | 1,000 | Water |

## Parachutes

| grid | reef | minAtmo | drag | radiusMult |
|---|---|---|---|---|
| Large | 0.6 | 0.2 | 1.0 | 8.0 |
| Small | 0.6 | 0.2 | 1.0 | 8.0 |

(parachuteAlgoVer = 1)

## Planets

| planet | gravity | atmosphere |
|---|---|---|
| [SSP] Jupiter | 20.0 | yes |
| [SSP] Neptune | 20.0 | yes |
| [SSP] Uranus | 20.0 | yes |
| sdx_saturnAdjusted | 20.0 | yes |
| [SSP] Saturn | 20.0 | yes |
| sdx_jupiterAdjusted | 2.52 | yes |
| Pertam | 1.2 | yes |
| Alien | 1.1 | yes |
| EarthLike | 1.0 | yes |
| Triton | 1.0 | yes |
| RealStar | 1.0 | no |
| [SSP] Earth | 1.0 | yes |
| Mars | 0.9 | yes |
| [SSP] Venus | 0.9 | yes |
| sdx_neptuneAdjusted | 0.89 | yes |
| sdx_uranusAdjusted | 0.89 | yes |
| Mars_E | 0.38 | yes |
| [SSP] Mercury | 0.37 | no |
| Moon | 0.25 | no |
| Europa | 0.25 | yes |
| Titan | 0.25 | yes |
| [SSP] Io | 0.18 | yes |
| [SSP] Luna | 0.16 | no |
| [SSP] Ganymede | 0.14 | no |
| [SSP] Titan | 0.14 | yes |
| [SSP] Europa | 0.13 | no |
| [SSP] Callisto | 0.12 | no |
| [SSP] Miranda | 0.08 | no |
| [SSP] Triton | 0.07 | no |
| [SSP] Pluto | 0.06 | yes |
| [SSP] Ariel | 0.05 | no |
| [SSP] Charon | 0.05 | no |
| [SSP] Oberon | 0.05 | no |
| [SSP] Titania | 0.05 | no |
| [SSP] Umbriel | 0.05 | no |
| Ceres | 0.05 | no |
| Deimos | 0.05 | no |
| Hygeia | 0.05 | no |
| Pallas | 0.05 | no |
| Phobos | 0.05 | no |
| Phoebe | 0.05 | no |
| Vesta | 0.05 | no |
| [SSP] Dione | 0.05 | no |
| [SSP] Enceladus | 0.05 | no |
| [SSP] Iapetus | 0.05 | no |
| [SSP] Mimas | 0.05 | no |
| [SSP] Rhea | 0.05 | no |
| [SSP] Tethys | 0.05 | no |

## Bulk catalogues (exported to CSV alongside this file)

- `sdx2_blocks.csv` — 2102 blocks with component recipes
- `sdx2_cargo.csv` — 38 cargo containers
- `sdx2_items.csv` — 96 items (mass/volume)
- `sdx2_components.csv` — 49 components with raw-material cost
- `sdx2_materials.csv` — 36 materials
