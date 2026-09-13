# MOABB release inventory for import conformance

This is the complete **static top-level export inventory** of the MOABB revision already
identified by the existing local conversion campaign and compact journey registry. It is an
acceptance denominator, **not a support certificate or a claim of 147 independent cohorts**.
Do not replace it with the subset that passes, or silently update it to the latest catalog.

## Identity and counting rule

- Registry release: MOABB 1.5.0, tag `v1.5`.
- Exact revision: `140809d8c48bdf2be953951ff75f688122edee34`.
- Source: [top-level exports](https://github.com/NeuroTechX/moabb/blob/140809d8c48bdf2be953951ff75f688122edee34/moabb/datasets/__init__.py)
  and [registration rules](https://github.com/NeuroTechX/moabb/blob/140809d8c48bdf2be953951ff75f688122edee34/moabb/datasets/utils.py).
- Count every named dataset export, retaining paradigm/subset variants and aggregate classes:
  **147 non-synthetic entries**. Do not merge Dreyer variants, BNCI entries, or Mainsah subsets
  merely to improve coverage. Their possible shared recordings do not count as independent data.
- Exclude the two explicitly synthetic exports, `FakeDataset` and `FakeVirtualRealityDataset`,
  from real-data acceptance, and exclude utility functions/dictionaries/module exports.
  Names in upstream `_REMOVED_DATASETS` are not active exports and are not resurrected.
- The retained Windows environment now has MOABB 1.5.0 for this campaign. Its installed Python and
  metadata files match the pinned commit; the wheel omits only two upstream test files. Offline runtime
  inspection constructed all 147 entries and found each inherited the official converter. The runtime
  registry contains exactly these entries plus the two excluded fake classes. This proves catalog and
  converter availability, not source access, loader execution or data conformance.
- Access, license and official conversion results remain per-entry checks. A shared version string alone
  does not prove the exact identity of an old conversion.

## Available evidence and missing scope

The retained local campaign has converted subsets for 15 entries. The E: conformance campaign adds
full-corpus and representative source/loader/conversion/import evidence across the inventory, including
BNCI, ERP Core, Mainsah2025, SSVEP, motor-imagery and recent-dataset lanes. The per-entry table and its
linked reports are authoritative for the exact coverage. That is currently **127 entries with runtime
evidence, 20 entries with a specific reviewed rights/data/loader blocker, and no entry left
undispositioned**. Payload/runtime disposition remains distinct from the stricter MOABB-to-EEG-BIDS
route disposition described below; a payload PASS must not be read as a BIDS-route PASS.
The stricter route review is also fully dispositioned: **110 representative route passes and 37 specific
route/source/license/loader/product blockers across all 147 exports, with no row left unexamined**.
The blocker count includes the 20 payload-level blockers and converter/product limitations on otherwise
readable payloads; it must not be presented as 37 unreadable datasets. After the embedded-event review
repair, all 20 Mainsah2025 exports and Zuo2025 pass retained-source BIDS-root Commands and recipe replay.
Yi2025 also passes the existing external-label route: its old missing-events receipt was incorrect,
and fresh source comparison confirms the retained events.tsv values and sample positions.
This does not prove their
original sources are unavailable
elsewhere. Acquisition requires source/license/size/cache review; absence is not PASS or exclusion.
Local source manifests and checksums do not by themselves prove conversion fidelity.

The first lexicographic recording of each of the 15 local entries was checked through the actual
Scan → Preview → Validate → Apply route, with all signal samples compared in chunks against the
independent MNE reader of the converted file, channel order against channels.tsv, and all event
sample positions/class text against events.tsv. These are bounded importer checks, **not a replay
of the official loader or all recordings/subjects**. The four converted format families were
BrainVision, EEGLAB, EDF and BDF. Exact selections/results remain in the local diagnostic output;
this page defines the denominator and evidence limits, not a new executable gate.

Keep original trigger numbers distinct from exporter or application IDs: names and sample
positions must match the reviewed mapping, while numeric identity changes must be traceable.
For cVEP, per-flash `0.0/1.0` labels are not trial-target labels. Thielen2021's separate
`trial_id` column requires its own reviewed meaning; bit-label import cannot certify the
20-target task. No label or trial reconstruction is inferred from counts alone.

A separate read-only cross-check covered all 10 retained Thielen recordings: 200 trial IDs and
their onsets matched the original MAT/GDF sources, and all EEG samples matched after the official
channel renaming within the explicitly checked float32 tolerance (relative 2e-7, absolute 1e-12 V).
This is source/export comparison, not proof of a complete 20-target product workflow. The first
diagnostic attempt used a MAT reader without v7.3 support; using the already installed upstream
reader resolved that harness failure without changing data or product code.

## Retained-source repair evidence

The embedded-label repair reruns select one usable recording per export; they do not download or
exercise every recording. All 22 rows pass fresh Scan/Preview/Validate/Apply, exact converted-waveform
readback and saved-recipe replay. The receipts bind the active worktree baseline plus exact hashes of
the six affected backend files; those hashes were independently checked before product commit.

Retained evidence below is under `E:\XBrainLabData\evidence`:

- Mainsah A–J: `mainsah2025-embedded-bids-retest-20260913/result-a-b-c-d-e-f-g-h-i-j-v7.json`,
  SHA-256 `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`.
- Mainsah K–S2: `mainsah2025-embedded-bids-retest-20260913/result-k-l-m-n-o-p-q-r-s1-s2-v7.json`,
  SHA-256 `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`.
  Each observed embedded event sequence matches a fresh retained-source MOABB loader run. Run P uses
  run 1 to include both classes; the selected runs and subjects are preserved per row.
- Zuo and Yi: `retained-zuo-yi-embedded-retest-20260913/result-v2.json`,
  SHA-256 `edd6b22dd795aa0547d7f0b9e849102562b05394fadc3036427f222a1b781ae7`.
  Zuo's two marker classes are checked against its original MAT loader. Yi uses its retained external
  events.tsv, not the new missing-sidecar path.
- Yi provenance correction: `moabb-ten-20260913/yi2025-provenance-correction-20260913/result-v2.json`,
  SHA-256 `45e4e18502dd2176f85579e24e85b0ff4986d9f3a7eed2b7434b4a979708cfcf`.
  All eight source class/sample sequences match the retained BIDS sidecars (40 events per run). Run 0
  compares all 789,000 samples across 62 channels; maximum voltage error is about 4.9e-11 V, below the
  declared export bound. Other runs check only three 64-sample waveform probes. The original converter
  script/log was not retained; the previous receipt records converter/options and the dataset identifies
  MOABB 1.5.0. This is a corrected retained-root result, not a claim of a newly observed conversion.

## Full export list

Module paths are relative to `moabb/datasets/` at the exact revision above. Availability combines the
retained and E: campaigns; each row still states its evidence limit and is not a product-support claim.

| Dataset export | Source module | Available runtime evidence |
| --- | --- | --- |
| AlexMI | `alex_mi` | Full 8-subject source/conversion evidence plus selected-run BIDS-root Command/readback/recipe PASS; aggregate receipt SHA-256 `d98657f1...8a09f0ea` |
| Rodrigues2017 | `alphawaves` | Full 19-subject converted-shape evidence plus selected-run BIDS-root Command/readback/recipe PASS; pinned loader path repair disclosed; aggregate receipt SHA-256 `d98657f1...8a09f0ea` |
| Shin2017A | `bbci_eeg_fnirs` | BLOCKED: pinned loader requires explicit user GPLv3 terms acceptance |
| Shin2017B | `bbci_eeg_fnirs` | BLOCKED: pinned loader requires explicit user GPLv3 terms acceptance |
| Beetl2021_A | `beetl` | Final-training subject 1 retained source fresh-loader → MOABB 1.5.0 EEG-BIDS → five-Command/readback/recipe PASS with 100 semantic `trial_type` events and exact 63-channel waveform fidelity (`aee746da0a4c10943a6802bdf52a6972d28c0c27037775bd87992bd93cf0b897`) |
| Beetl2021_B | `beetl` | Final-training subject 4 retained source fresh-loader → MOABB 1.5.0 EEG-BIDS → five-Command/readback/recipe PASS with 120 semantic `trial_type` events and exact 32-channel waveform fidelity (`05c86d7e3594983e87566fda9ea3e71aeba2bafe8cb32fe9c70b00878a5eb347`) |
| BNCI2003_004 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`89282b2124b4ec49887a847e1da27a902a167f72d167bd97ea07b98e8a5be1d4`) |
| BNCI2014_001 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `EOG1`, `EOG2` and `EOG3` channels (`7fd1ab1ab1f48ced1b4aeff177b867ebd5dbfe6b04b5fc1ca105573e0045cfae`) |
| BNCI2014_002 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`ee2c25a6e32939230e4c4e5a9255ebe5d3295de0c975f455fb6d27f1d0143099`) |
| BNCI2014_004 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `EOG1`, `EOG2` and `EOG3` channels (`31ca7318807d5cec3a13c42eec608fcee1427b52c9546d52ed84101697dd8e4e`) |
| BNCI2014_008 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with source/BIDS channel, waveform and event fidelity (`4e956b42361d502d1c94054a7e1200788df54a8f81e1d7f22221fcb54762dcd3`) |
| BNCI2014_009 | `bnci` | Subject 1 session-0 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with deterministic source pairing and source/BIDS fidelity (`2e1991da61b284bfd8fa8a5d6a5bf1a96308abea3b77ab1009fcdbbc09acd2eb`) |
| BNCI2015_001 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with source/BIDS channel, waveform and event fidelity (`fb3841b4100d4e99fba98d31ded799de9a121367735c6e0cc3744507da249058`) |
| BNCI2015_003 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with source/BIDS channel, waveform and event fidelity (`89afc2ad7ffb9effa7d4a55bc3d90ac2e3ae17f2e4085e81b0c4fe610e10a331`) |
| BNCI2015_004 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with source/BIDS channel, waveform and event fidelity (`0c4f85c44ca79d4728f5527cc0629635dbc41d09e095246a99c23476dca1accc`) |
| BNCI2015_006 | `bnci` | BLOCKED: pinned loader rejects 973 events shorter than its shortest-event rule |
| BNCI2015_007 | `bnci` | Subject 1 run-0 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with event-based deterministic pairing and source/BIDS fidelity (`0c7fc78b800285afdcc37271968da8ff46f194ba6455d8c8a45bcd4f90223927`) |
| BNCI2015_008 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`aef8321d0c5e35ab62f4a6da2b5940f7d77bd5608898b475b3940474f3c5abaa`) |
| BNCI2015_009 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `EOGv` and `EOGh` channels (`817a844c97bb65c16f03c8dc5c592e89d7e0996eaa4ed691aa89b4a5ff1d5ed8`) |
| BNCI2015_010 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`4b9cb4fada146d43e8c3509eff49f047d4a9dc0e09df7ded3bc115717b6ebea8`) |
| BNCI2015_012 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`f5dd6882bd35220e6a9b448b13e99df0f19ecf99fc0d3fc932c2cd50f6bd91d9`) |
| BNCI2015_013 | `bnci` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`03313fcfa79a930e5dc84d6183b8279f124265b5fd6becacc830f3532de8b39f`) |
| BNCI2016_002 | `bnci` | BLOCKED: pinned loader raises `KeyError: 88` for representative subject 1 |
| BNCI2019_001 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `eog-l`, `eog-m` and `eog-r` channels (`eda14cab55fdb59bc87897ec82bc40545aa387b44134723f026649e069862b99`) |
| BNCI2020_001 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits six source EOG channels (`77146c1b177e4dbffd6bb69ce61a97c899337e6106af3d6e5550d583b6e77e66`) |
| BNCI2020_002 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `HEOG` and `VEOG` channels (`38188b2c978830cf0b161c2dd3127a2ae87ab99712870e3f09c6c768db58d5b5`) |
| BNCI2022_001 | `bnci` | BLOCKED: pinned loader finds no stim channel in representative subject 1 |
| BNCI2024_001 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `EOG1`–`EOG4` channels (`5e3f5dc0bf61c8a4a3baddb135ace41611d2de308befce852e03863265434e26`) |
| BNCI2025_001 | `bnci` | BLOCKED: duplicate timestamp rows resolve to EEG sample 8613 and atomic Apply rejects them |
| BNCI2025_002 | `bnci` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `VEOG1`, `VEOG2`, `HEOG1` and `HEOG2` channels (`af0bad800e7e858b8b403ae0a2ea626f37a8e3474328cdf923b0fe737da8703b`); the selected run exposes only `snakerun` and is not supervised-ready |
| BI2012 | `braininvaders` | Payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`fed0abd4...ad02e8d`); pinned loader path workaround disclosed |
| BI2013a | `braininvaders` | Subject 1 selected run loader → retained EEG-BIDS root → BIDS-root Command evidence; official archive MD5 values retained |
| BI2014a | `braininvaders` | Payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`fed0abd4...ad02e8d`); 64-subject loader versus 71-subject record-description limit disclosed |
| BI2014b | `braininvaders` | Payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`fed0abd4...ad02e8d`); pinned adapter omits collaborative recording |
| BI2015a | `braininvaders` | Subject 1 payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`fed0abd4...ad02e8d`) |
| BI2015b | `braininvaders` | Subjects 1/2 payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`fed0abd4...ad02e8d`) |
| Cattan2019_VR | `braininvaders` | Subjects 1/21 PC+VR payload evidence; selected-run MOABB-1.5.0 BIDS-root five-Command/exact-readback PASS (`e5a20362...c6464b08`); pinned loader path contradiction disclosed |
| Brandl2020 | `brandl2020` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`e111d1e825086d21430c521b45cfbe074698870b3dc3011faf07f773324089b2`); process-local relative-junction seam avoids the pinned Windows path sanitizer |
| CastillosBurstVEP40 | `castillos2023` | Subject 2 conversion plus selected-run BIDS-root Command/readback/recipe PASS; Windows cache workaround disclosed; aggregate receipt SHA-256 `d98657f1...8a09f0ea` |
| CastillosBurstVEP100 | `castillos2023` | Subject 1 conversion plus selected-run BIDS-root Command/readback/recipe PASS; Windows cache workaround disclosed; aggregate receipt SHA-256 `d98657f1...8a09f0ea` |
| CastillosCVEP40 | `castillos2023` | Subject 4 conversion plus selected-run BIDS-root Command/readback/recipe PASS; Windows cache workaround disclosed; aggregate receipt SHA-256 `d98657f1...8a09f0ea` |
| CastillosCVEP100 | `castillos2023` | Subject 3 conversion plus selected-run BIDS-root Command/readback/recipe PASS; Windows cache workaround disclosed; aggregate receipt SHA-256 `d98657f1...8a09f0ea` |
| Chailloux2020 | `chailloux2020` | Subject 1 full pinned 15-run source/BrainVision/BIDS-root Command/readback/event/recipe evidence; 45 OpenNeuro ds003190 CC0 assets and the converter child BIDS root are retained atomically on E:, independently re-read aggregate receipt SHA-256 `87dc487d...59b8850c` |
| Chang2025 | `chang2025` | Subject 6 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity; only STIM is externalized (`09a099d7eee3c0aaf4f40c7fb3b7c19ab873777eef7a6ac2e2824e2736968ce5`) |
| Dreyer2023 | `dreyer2023` | Official source-BIDS selected-run five-Command/exact-readback PASS; aggregate maps explicitly to Dreyer2023A subject 1 (`e5a20362...c6464b08`) |
| Dreyer2023A | `dreyer2023` | Subject 1 official source-BIDS selected-run five-Command/exact-readback PASS with reviewed 769/770 class mapping (`e5a20362...c6464b08`) |
| Dreyer2023B | `dreyer2023` | Subject 61 official source-BIDS selected-run five-Command/exact-readback PASS with reviewed 769/770 class mapping (`e5a20362...c6464b08`) |
| Dreyer2023C | `dreyer2023` | Subject 82 official source-BIDS selected-run five-Command/exact-readback PASS with reviewed 769/770 class mapping (`e5a20362...c6464b08`) |
| EPFLP300 | `epfl` | BLOCKED: official academic host and adapter provide no explicit source-data license or published checksum |
| ErpCore2021_ERN | `erpcore2021` | Subject 1 source-BIDS/Command evidence; evidence mapping keeps stimulus and excludes response |
| ErpCore2021_LRP | `erpcore2021` | Subject 1 source-BIDS/Command evidence; evidence mapping keeps stimulus and excludes response |
| ErpCore2021_MMN | `erpcore2021` | Subject 1 source-BIDS/Command evidence; evidence mapping keeps stimulus and excludes response/STATUS |
| ErpCore2021_N2pc | `erpcore2021` | Subject 1 source-BIDS/Command evidence; evidence mapping keeps stimulus and excludes response |
| ErpCore2021_N170 | `erpcore2021` | Subject 1 source-BIDS/Command evidence; evidence mapping keeps stimulus and excludes response |
| ErpCore2021_N400 | `erpcore2021` | Subject 1 source-BIDS/Command evidence; evidence mapping keeps stimulus and excludes response |
| ErpCore2021_P3 | `erpcore2021` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Forenzo2023 | `forenzo2023` | Subject 1 retained source fresh-loader → existing MOABB 1.5.0 EEG-BIDS root → five-Command/readback/recipe PASS (`4377285aa305221f8e6d2bcfc0ff836926465e0e59f11a813fc8d7e43b209712`) |
| Gao2026 | `gao2026` | Subject 9 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity (`350fcac5da18167b1e00ee6c59029a824d24730e67649e9778589b07dbb42032`) |
| Cho2017 | `gigadb` | Subject 1 selected run loader → retained EEG-BIDS root → BIDS-root Command evidence; official source has no published cryptographic checksum |
| GuttmannFlury2025_ME | `guttmann_flury2025` | Subject 1 retained source fresh-loader → MOABB 1.5.0 EEG-BIDS → five-Command/readback/recipe PASS with strict source/BIDS fidelity (`04edab69f125c015ee35fa53be5eebbef0ff56de521ee2944720a02c7cf376e7`); exporter incomplete-head-dig seam disclosed |
| GuttmannFlury2025_MI | `guttmann_flury2025` | Subject 1 retained source fresh-loader → MOABB 1.5.0 EEG-BIDS → five-Command/readback/recipe PASS with strict source/BIDS fidelity (`5be9001b66b0f395338888b82e43da6d6f511bf4be0f51ef34a746311e98e89f`); exporter incomplete-head-dig seam disclosed |
| GuttmannFlury2025_P300 | `guttmann_flury2025` | Subject 1 default 4L retained source fresh-loader → MOABB 1.5.0 EEG-BIDS → five-Command/readback/recipe PASS with strict source/BIDS fidelity (`d4a730dfd85c5269e1d39fbca352bede60225bce288fd1c34b19a4c091af34c5`); exporter incomplete-head-dig seam disclosed |
| GuttmannFlury2025_SSVEP | `guttmann_flury2025` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| HefmiIch2025 | `hefmi_ich2025` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with fresh-loader source/BIDS fidelity; only STI is externalized (`d0a541974e6c52b6460e544b54ee4a23827b0be8d8cf3840c0a2eaa7ad6abaf3`); receipt supersedes an exact-file identity race |
| Hinss2021 | `hinss2021` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Huebner2017 | `huebner_llp` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found six omitted source misc channels (`EOGvu`, `x_EMGl`, `x_GSR`, `x_Respi`, `x_Pulse`, `x_Optic`; `82a04ba36c373d8770dd7e12fa694259694316717bed8d89fdb5c0f2aa3010fd`), superseding the alias-mutated receipt |
| Huebner2018 | `huebner_llp` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found six omitted source misc channels (`EOGvu`, `x_EMGl`, `x_GSR`, `x_Respi`, `x_Pulse`, `x_Optic`; `089e8bffecc54da8b4fd69c0026840a1e0d6bc4c1ae0c6c8455bcf45e2fad4a5`), superseding the alias-mutated receipt |
| Jeong2020 | `jeong2020` | Subject 1 official-MD5 loader/BrainVision/Command evidence; selected-run MOABB EEG-BIDS/BIDS-root Command/readback/recipe evidence, receipt SHA-256 `474ce0bc...a5a954c` |
| Kaneshiro2015 | `kaneshiro2015` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`05735ef7...f8d8a798`) |
| Kaya2018 | `kaya2018` | Subject 1 selected run loader → retained EEG-BIDS root → BIDS-root Command evidence; official file MD5 retained |
| Kojima2024A | `kojima2024a` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader/source audit found that conversion omits source `vEOG` and `hEOG` channels (`c8786bfc4e8ceefac8b75612358fe6b0548de5fcadef594b3394fb48878fc707`) |
| Kojima2024B | `kojima2024b` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a deterministic fresh source/BIDS pair differs by 40 samples (424480 versus 424520 at 1000 Hz); both expose 240 events but event semantics are not certified across the length mismatch (`981147915484a8e6b4a2084562c9cb2b6453569e4b2ce460deda1f119436488b`) |
| Kumar2024 | `kumar2024` | Subject 1 retained source fresh-loader → existing MOABB 1.5.0 EEG-BIDS root → five-Command/readback/recipe PASS with exact channel, rate, sample, waveform and event fidelity (`b1558ae413b031daabd86b667f3ed7f37e3510ece1b7bfe50ad84961b5a57fc2`) |
| Lee2019_ERP | `Lee2019` | Subject 1 payload evidence plus retained MOABB-1.5.0 BIDS-root five-Command/exact-readback PASS (`e5a20362...c6464b08`); pinned selected-session defect disclosed |
| Lee2019_MI | `Lee2019` | Subject 1 payload evidence plus retained MOABB-1.5.0 BIDS-root five-Command/exact-readback PASS (`e5a20362...c6464b08`); pinned selected-session defect disclosed |
| Lee2019_SSVEP | `Lee2019` | Subject 1 payload evidence plus retained MOABB-1.5.0 BIDS-root five-Command/exact-readback PASS (`e5a20362...c6464b08`); pinned selected-session defect disclosed |
| Lee2021Mobile_ERP | `lee2021_mobile` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Lee2021Mobile_SSVEP | `lee2021_mobile` | Subject 1 session 2 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`d4fb023f...3bfa9d6`); supplemental fresh public-loader audit confirms source/non-STIM channel, event and waveform fidelity (`5bec1714f50f9c1820c4780a09f095a824387b758d6f278989d51afec3537a7f`) |
| Lee2024_AC | `lee2024` | BLOCKED: official repository has no declared or included source-data license |
| Lee2024_BS | `lee2024` | BLOCKED: official repository has no declared or included source-data license |
| Lee2024_DL | `lee2024` | BLOCKED: official repository has no declared or included source-data license |
| Lee2024_EL | `lee2024` | BLOCKED: official repository has no declared or included source-data license |
| Lee2024_TV | `lee2024` | BLOCKED: official repository has no declared or included source-data license |
| Liu2024 | `liu2024` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader/source audit found that conversion omits source `HEOL` and `VEOR` EOG channels (`dac50e9376ffe4bd31bd1234782b4698e604812cd5aceabefc9adf2c1c8c27ca`) |
| Liu2025 | `liu2025` | Subject 6 verified retained archive fresh-loader → MOABB 1.5.0 EEG-BIDS → five-Command/readback/recipe PASS with strict source/BIDS fidelity (`beefff38b9d40a70f38224201458e675bd8a32f5bbc65db9924206676f3fe9d3`); task-local extraction was removed after receipt publication |
| Ma2020 | `ma2020` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Mainsah2025_A | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_B | `mainsah2025` | Subject 8, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_C | `mainsah2025` | Subject 18, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_D | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_E | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_F | `mainsah2025` | Subject 3, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_G | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_H | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_I | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_J | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `d4cebbde8c7a34f39b7d9080f0dcb6114151d1ed1abaace8cb8339fbebbd7014`) |
| Mainsah2025_K | `mainsah2025` | Subject 2, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_L | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_M | `mainsah2025` | Subject 4, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_N | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_O | `mainsah2025` | Subject 14, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_P | `mainsah2025` | Subject 1, run 1: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_Q | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_R | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_S1 | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| Mainsah2025_S2 | `mainsah2025` | Subject 1, run 0: retained official converter root → complete embedded `NonTarget`/`Target` review → Commands/readback/recipe replay PASS; fresh loader marker sequence matches exactly (rerun receipt `8ed3105a3fa070f48d693602ff86a2d34a43d0b04107a61168f5c8c9deba8a39`) |
| MartinezCagigal2023Checker | `martinezcagigal2023_checker_cvep` | SF01 fresh MOABB-to-BIDS five-Command/readback/recipe PASS under a measured same-source float32 relative-error bound (`04793d0c...e697bcb`); supplemental fresh public-loader audit confirms source/non-STIM channel, event and bounded waveform fidelity (`7a973c7dd26e4d7977becac8d29dd50c04c31d295dd07b26bfc3c5f5254ca506`) |
| MartinezCagigal2023Pary | `martinezcagigal2023_pary_cvep` | BLOCKED: exact official source failed two independent bounded Windows-native connections |
| GrosseWentrup2009 | `mpi_mi` | Subject 1 selected run loader → retained EEG-BIDS root → BIDS-root Command evidence; both official MD5 values retained |
| Cattan2019_PHMD | `phmd_ml` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`263997fe...77f99ad`); supplemental fresh public-loader audit confirms source/non-STIM channel, event and waveform fidelity (`142d6ad8a27ee241ee3c6802213df5f06f4fa1eddc2eb005265ef2dcffe28aa6`) |
| PhysionetMI | `physionet_mi` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| RomaniBF2025ERP | `romani_bf2025_erp` | Representative source/loader/BrainVision/Command evidence; nested BIDS-root seam disclosed |
| Rozado2015 | `rozado2015` | BLOCKED: pinned RAR extraction requires unrar, unar, or 7z, none present in retained environment |
| Schirrmeister2017 | `schirrmeister2017` | Subject 1 train selected run fresh MOABB-to-BIDS Scan/Preview/Validate/Apply, waveform/event readback and recipe-root identity PASS; retained child receipt SHA-256 `cbd252420865dd2a176ec9c587fbf6afe9a68302ba0617219bafff29ece70af3` |
| Simoes2020 | `simoes2020` | Subject 1 payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`296c1c46...57ebe9f`) |
| Sosulski2019 | `sosulski2019` | BLOCKED: pinned loader exposes only one 4.58 GB all-subject archive, with no representative source unit |
| Speier2017 | `speier2017` | Subject 1 complete payload evidence plus selected-run fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`478c1868...61c0be60`); supplemental fresh public-loader audit confirms source/non-STIM channel, event and waveform fidelity (`770483d1f1dcb44ddd8b0569b267227a3bdbf449daa5d5efb2539ba7dcf63cc9`) |
| Chen2017SingleFlicker | `ssvep_chen2017` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Dong2023 | `ssvep_dong2023` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`eca6c948...98a0c022`); supplemental fresh public-loader audit confirms only STIM was externalized and preserves source channels/events/readback (`9c664edcd135ef44806f9eb6c087d23772f4373f32e4b86fd69b177b85738c1b`) |
| Kalunga2016 | `ssvep_exo` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`0273cb23...48677c0e`); supplemental fresh public-loader audit confirms only STIM was externalized and preserves source channels/events/readback (`bff167fc714a61e16bad4cb67f0a2f1cde7143725fcf5372a64a7727593ff040`) |
| Han2024Fatigue | `ssvep_han2024` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`08f14424...9f8d052b`); supplemental fresh public-loader audit confirms source/non-STIM channel, event and waveform fidelity (`e0da6d7c83a5bffb8bfcf2a2376f9f970ee8942d6e81d7bc7e36fa28b6d61563`) |
| Kim2025BetaRange | `ssvep_kim2025` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits non-STIM `M1` and `M2` misc channels (`9538ae3ce52aa0f9283906e6d2819437b6bbc391d3935f3af30452f2db9f1198`), superseding the alias-mutated apparent PASS |
| Liu2020BETA | `ssvep_liu2020` | BLOCKED: source only states non-commercial research use; no public CC license or official checksum |
| Liu2022EldBETA | `ssvep_liu2022` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS (`ddcb2816...cc0d9beb`); supplemental fresh public-loader audit confirms source/non-STIM channel, event and waveform fidelity (`df52466989075913191895475d34c39d22228ec3e758826fe99d1c6e6cd9baf4`) |
| MAMEM1 | `ssvep_mamem` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| MAMEM2 | `ssvep_mamem` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with converter-derived quantization bound (`bee42ce8...fbb0ff2`) |
| MAMEM3 | `ssvep_mamem` | Subject 1 fresh MOABB-to-BIDS five-Command/readback/recipe PASS with converter-derived quantization bound (`372f5bd6...749bfec2`) |
| Nakanishi2015 | `ssvep_nakanishi` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Wang2016 | `ssvep_wang` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Wang2021Combined | `ssvep_wang2021` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** because a fresh public-loader audit found that conversion omits source `HEOG` and `VEOG` channels (`d98afa9a33fd363e88215fe4cb2ea5121d2fec8923e3053da6ef0493d4b43c6c`), superseding the alias-mutated apparent PASS |
| Stieger2021 | `stieger2021` | Subject 1 session 1 run 0 fresh MOABB-to-BIDS Scan/Preview/Validate/Apply, waveform/event readback and recipe-root identity PASS; retained child receipt SHA-256 `25e7f5b55dfe3c07857f778981002bb0f20ccca2968706bb699eaa584492fcdd` |
| Tavakolan2017 | `tavakolan2017` | BLOCKED: pinned loader requires missing BCI2kReader after finding all four subject-1 DAT files |
| Thielen2015 | `thielen2015` | BLOCKED: semantic trial labels live only in annotation extras, which BrainVision drops |
| Thielen2021 | `thielen2021` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| TrianaGuzman2024 | `triana_guzman2024` | Payload/BIDS Command route PASS; **source-to-export metadata fidelity BLOCKED** because the fresh public loader exposes `STIM` as EEG while the export types the same preserved channel as STIM (`b7cae31e7f8bd4f75b53ec5393623e3e1ed45e0b0fd27f87a3191c38076de5c2`); export-only invalid-fiducial seam disclosed |
| Ofner2017 | `upper_limb` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Wairagkar2018 | `wairagkar2018` | Subject 1 session 0 run 0 fresh MOABB-to-BIDS Scan/Preview/Validate/Apply, waveform/event readback and recipe-root identity PASS; retained child receipt SHA-256 `af3de6caca1519ec5b4cd5c74d74431e35bcc14e42a88b364a3a79cc00431406` |
| Weibo2014 | `Weibo2014` | Payload route PASS; **MOABB-to-BIDS conversion BLOCKED** after a fresh public-loader audit found four omitted non-STIM channels; the receipt also retains an unresolved source-trigger/BIDS event offset and class-order difference instead of masking it (`c1ecc6df2ad20b336e545ac650b1ebfc92881267c1e265c496bf282f3e2c8ac2`), superseding the alias-mutated apparent PASS |
| Wu2020 | `wu2020` | Subject 1 payload evidence plus retained MOABB-1.5.0 BIDS-root five-Command/exact-readback PASS (`e5a20362...c6464b08`); official EEG-only channel selection recorded |
| Yang2025 | `yang2025` | BLOCKED: pinned loader exposes only one 65.6 GB corpus archive, with no representative source unit |
| Yi2025 | `yi2025` | Subject 11 retained MOABB 1.5.0 BIDS root has eight events.tsv files; all eight source event sequences match, and selected run-0 Commands/readback/recipe replay PASS (`edd6b22dd795aa0547d7f0b9e849102562b05394fadc3036427f222a1b781ae7`). The earlier missing-events receipt was incorrect; historical converter script/log is unavailable, so retained options/provenance are disclosed rather than described as a fresh conversion |
| Zhang2017 | `zhang2017` | BLOCKED: pinned RAR extraction requires an external extractor absent from the retained environment |
| Zhang2025 | `zhang2025` | Subject 1 retained source fresh-loader → existing MOABB 1.5.0 EEG-BIDS root → five-Command/readback/recipe PASS (`f04a76f5cc39223b07ea2f23d027551ab2a67c1991c51e931ba4f20e393ebd32`); process-only pinned output-path seam disclosed |
| Zheng2020 | `zheng2020` | Subject 1 session 0 run 0 fresh MOABB-to-BIDS Scan/Preview/Validate/Apply, waveform/event readback and recipe-root identity PASS; retained child receipt SHA-256 `986dc316b581d3a6f20d9d38f837dd87394daba5ede07f4f7e48e6b0cd15db66` |
| Zhou2016 | `Zhou2016` | Subject 1 retained source plus root metadata fresh MOABB-to-BIDS five-Command/readback/recipe PASS; independent public-loader identity remained stable across conversion (`0d2ab582820e68fb3d4aa966b768c7488e099547970eb7328ae28c64d041247f`) |
| Zhou2020 | `zhou2020` | Retained MOABB 1.5 BIDS root selected-run Command/readback/recipe PASS; original converter options were not persisted; aggregate SHA-256 `62ef6cdb...49ac4c53` |
| Zuo2025 | `zuo2025` | Retained source/official BIDS embedded markers match the fresh loader as `Stimulus/S  1`→`left_leg`, `Stimulus/S  2`→`right_leg`; complete reviewed Commands, exact readback and recipe replay PASS (`edd6b22dd795aa0547d7f0b9e849102562b05394fadc3036427f222a1b781ae7`), superseding the missing-events product blocker |

See [the validation contract](README.md#import-support-claims) for the required conversion and
Command evidence, and the user guide for the accepted format/label boundary. This inventory does
not narrow that boundary to MOABB or to the local 15 entries.
