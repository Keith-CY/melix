# Imagenette Evaluation Fixture

This fixture is a repository-owned 10-sample validation subset derived from
`frgfm/imagenette` on Hugging Face.

Provenance:

- source dataset: `https://huggingface.co/datasets/frgfm/imagenette`
- source config: `160px`
- source split: `validation`
- source license: Apache-2.0

Fixture policy:

- one deterministic sample per Imagenette class
- image files downloaded from the Hugging Face dataset rows API
- prompt phrased as short closed-set image classification QA so the current
  Melix exact-match scorer can grade responses without introducing a new
  classifier-specific scorer

The selected classes are:

- `tench`
- `English springer`
- `cassette player`
- `chain saw`
- `church`
- `French horn`
- `garbage truck`
- `gas pump`
- `golf ball`
- `parachute`
