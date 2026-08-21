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

No CC-BY-NC or patent-restricted model source is included. In particular,
EEGMiner, MetaNeuromotorHand, EMG2QwertyNet, BrainModule, and the
GeneralizedGaussianFilter implementation are excluded from this namespace.
