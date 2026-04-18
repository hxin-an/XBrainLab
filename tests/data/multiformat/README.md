These fixtures are compact real-signal derivatives of `tests/data/A01T.gdf`.

They were generated from a 15-second slice of the real recording using 8 channels
to keep disk usage low while still exercising real import paths across multiple
extensions.

Included fixture set:

- `A01T-mini-real_raw.fif`
- `A01T-mini-real_raw.fif.gz`
- `A01T-mini-real-epo.fif`
- `A01T-mini-real.edf`
- `A01T-mini-real.bdf`
- `A01T-mini-real.vhdr`
- `A01T-mini-real.eeg`
- `A01T-mini-real.vmrk`
- `A01T-mini-real.set`

Purpose:

- keep a small cross-format regression baseline in-repo
- validate real loader behavior for several supported extensions
- avoid downloading larger external datasets for every test run
