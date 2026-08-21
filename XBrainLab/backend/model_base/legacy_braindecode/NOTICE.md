# Legacy Braindecode source notice

This namespace contains source adapted from `braindecode==1.6.1`, pinned by
the wheel and per-file hashes recorded in `PROVENANCE.tsv` and
`SUPPORT_PROVENANCE.tsv`. The upstream source is:

<https://github.com/braindecode/braindecode/tree/v1.6.1>

The copied model and support sources retain their author and license headers.
XBrainLab changed executable imports to the private
`XBrainLab.backend.model_base.legacy_braindecode` namespace. The local
`EEGModuleMixin` keeps only signal dimensions, output-shape inference, and
state-dict key translation; upstream Hub, remote download, model discovery,
and configuration serialization behavior are deliberately excluded. The
local `np_to_th` helper is likewise a minimal adaptation.

Braindecode source without a file-level override is distributed under the
BSD 3-Clause license in `LICENSE-BSD-3-Clause.txt`. Support modules are
symbol-level subsets containing only the primitives required by the models in
this family; unrelated upstream implementations are not copied in advance.

The vendored IFNet adaptation retains its upstream MIT notice in
`LICENSE-MIT-IFNet.txt`.

CTNet, MEDFormer, and TCFormer retain their MIT source headers; the standard
license text is included in `LICENSE-MIT.txt`. MVPFormer retains its IBM and
Apache-2.0 source notice; the Apache License 2.0 text is included in
`LICENSE-Apache-2.0.txt`.

The legacy STEEGFormer adaptation intentionally removes the upstream Hub
channel-vocabulary lookup. With no montage metadata it retains the documented
identity mapping; with `chs_info`, callers must supply a reviewed
`chan_pos_idx` explicitly. No legacy model downloads metadata or weights.

No CC-BY-NC or patent-restricted model source is included. In particular,
EEGMiner, MetaNeuromotorHand, EMG2QwertyNet, BrainModule, and the
GeneralizedGaussianFilter implementation are excluded from this namespace.
