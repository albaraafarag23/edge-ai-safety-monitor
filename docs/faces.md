# Face recognition

The detector can put a name on the people it sees, from photos enrolled per person. Names appear on the live
view, in incidents ("Who"), in reports and alert emails (always as an automatic identification to confirm).
A clear face that matches nobody enrolled is marked `unknown`.

## Setting it up
1. `scripts/get-face-models.sh` downloads the two models into `models/` (about 175 MB). On the Jetson, run it
   there too (or copy the two `.onnx` files to `~/sitesentry/models`).
2. Restart the detector: `docker compose up -d --build cv_pipeline`. Its log says
   `Face recognition: on (...)`.
3. In the console, **People** (admins): add a person, then their photos. Each photo is checked within a few
   seconds and marked Good or with what is wrong (no face, face too small, more than one face, looks like
   someone else). Photos can also be copied in by hand: `faces/<person_id>/*.jpg` plus an optional
   `person.json` (`{"name": "...", "name_ar": "..."}`).

Settings (`.env`): `FACE_RECOGNITION=auto|off`, `FACE_DEVICE=cpu|cuda`, and for tuning `FACE_MATCH` (0.38),
`FACE_STRONG` (0.50), `FACE_MIN_PX` (28).

## Photos: how many and what kind
**8 to 10 per person is ideal, 5 is the minimum for reliable results.** Variety matters more than number:

- One person per photo. Face sharp, well lit, at least ~200 px wide in the photo (any phone photo from
  about 1 m is far more than enough). Original files, not screenshots or heavily compressed copies.
- 3 or 4 looking straight at the camera, neutral or a light smile.
- 2 turned a little to the left and to the right (about 30 degrees, both eyes still visible), 1 or 2 looking
  slightly down, as a camera mounted high sees people.
- 2 or 3 wearing the hard hat they wear on site. Glasses on if they normally wear them.
- Some indoors, some outdoors in daylight.
- Best of all, 2 or 3 taken with the site camera itself from 2-4 m ("Save frame" on the Live cameras page,
  then crop to the person): they match what the detector will actually see.
- Avoid: sunglasses, masks, hands or phones over the face, beauty filters, strong backlight, group photos,
  photos older than a year or two.

## How it works
- **YuNet** (OpenCV's face detector, MIT licence) finds the face and its eyes, nose and mouth corners; the face
  is straightened to a 112x112 picture.
- **ArcFace ResNet-50** trained on WebFace600K (InsightFace "buffalo_l") turns it into 512 numbers. Faces of the
  same person give nearly the same numbers (cosine similarity).
- Each person is followed across frames (`cv_pipeline/tracker.py`). The face thread (`cv_pipeline/faces.py`)
  looks at each tracked person every 0.4 s until it is sure, reading the face from the **full-resolution**
  frame (detection itself runs on the half-size frame). A name is given after one strong match (>= 0.50) or two
  normal ones (>= 0.38), each at least 0.05 ahead of the next most similar person, and then stays with that
  person while they are in view, also when they turn away. It is checked again every 3 s and dropped if the
  face stops matching. Four clear looks with no match: `unknown`.
- It runs in its own thread on the CPU (2 threads by default), so it does not slow detection.

## Accuracy (measured 2026-11-15)
LFW, 40 people enrolled with 6 photos each, tested on 240 other photos of them and 400 strangers:

| Face width in the frame | Named correctly | Named as the wrong person | Stranger given a name |
|---|---|---|---|
| ~110 px | 99.6% | 0% | 0% |
| 48 px | 99.2% | 0% | 0% |
| 36 px | 100% | 0% | 0% |
| 28 px | 99.6% | 0% | 0% |
| 22 px | 99.2% | 0% | 0% |

(threshold 0.38; smaller faces were made by shrinking the photos.) These are clean press photos; a real camera
adds motion blur, steep angles and hard hats' shadows, so expect less, and measure it on the site camera before
quoting numbers. With the Arducam at 1080p (6 mm lens) a face is about 60 px wide at 5 m, 37 px at 8 m and
25 px at 12 m, so recognition should work to roughly 8-10 m when the person faces the camera, and not beyond.
Faces narrower than 28 px are not judged at all.

## The per-person tally

Analytics has a "By person" card: how many violations each enrolled person has, with the kinds, and a link to
the incidents counted. It counts only when it is sure, so the numbers are minimums:

- the face match was strong (`face_score` ≥ 0.50; a name settled by two weaker looks is shown in the incident
  but not counted). `TALLY_MIN_FACE_SCORE` on the event engine changes the bar;
- the person is the one who broke the rule: the one without the hard hat, the one smoking, the one inside the
  zone. Someone merely standing in the picture is not counted;
- the rule is one a single person breaks. Too many people on a scaffold counts nobody, and neither does a rule
  the plugin marks `"personal": false` (a person down).

A violation that goes on is counted once: a rule fires again every 10 s while it lasts, but only the first of
those incidents counts, until the person has kept the rule for 5 minutes (`TALLY_GAP_S`).

The event engine decides this when the incident fires and stores it as `metadata.violators`
(`event_engine/rules.py:_violators`, docs/contracts.md). Incidents from before this was added are not counted.

## Limits and care
- It needs to see the face: a person walking away, looking down under a hard hat, or far off stays unnamed.
- An incident keeps the names known at the moment it fired; a name learned a second later is not added.
- Identical twins and very similar relatives can be confused. Treat every name as a lead to confirm.
- **Personal data.** Face photos never leave the machine, are git-ignored, and only admins can see or change
  them. Enrol people only with their agreement, and remove them (People page) when they leave.
- **Licence.** InsightFace's trained models are for non-commercial research use. That covers this graduation
  project; a commercial product must license them or switch the recognition model (the code only needs an
  ONNX model that takes a 112x112 aligned face).
