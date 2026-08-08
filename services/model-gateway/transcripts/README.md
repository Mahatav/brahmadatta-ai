# Recorded transcripts

Empty on purpose.

Issue #82's last acceptance criterion: *"capture the transcripts on D5/D6 from real runs; a
transcript nobody recorded is not a fallback."* Committing a hand-written file here would
turn the fallback into a hand-written patch wearing a model's provenance, which is the
substitution the whole feature exists to prevent.

Transcripts arrive here by running the gateway in live mode — `RecordingSource` captures
every successful response automatically, so capture is not a step anyone has to remember at
2am on day six.

A file written by hand rather than captured must set `"capture_kind": "SYNTHETIC_FIXTURE"`.
The store refuses to serve one unless `MODEL_ALLOW_SYNTHETIC_TRANSCRIPTS=1` is set, and the
only place that is set is the test suite.

Check what is here:

    python -m gateway.tools.transcripts_cli list
    python -m gateway.tools.transcripts_cli verify
