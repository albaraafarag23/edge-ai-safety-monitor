# Team notes

Open questions for the team, with what we know so far.

## 1. Should we agree on one resize for all the pictures in our datasets?

**Short answer:** we need to agree on one *image size setting* (`imgsz`), but we don't need to resize the picture
files ourselves.

- YOLO resizes every picture automatically, during training and when detecting. It shrinks the picture to the `imgsz`
  we choose and fills the leftover space with grey bars, so nothing gets stretched. Pictures of different sizes in the
  same dataset are fine.
- What must match is the `imgsz` we train with and the `imgsz` we detect with. Our current model
  (`models/construction_ppe.pt`) was trained at **960**, and the plugin runs it at 960.
- The size trades distance for speed. At 640, hard hats are reliable up to about 12 m from the camera; at 960, about
  18 m; at 1280, about 23 m. Bigger is slower on the Jetson. If 960 is too slow there, we have a 640 model
  (`models/construction_ppe_640.pt`).
- Something that matters more than picture size when combining datasets: **how the boxes are drawn**. When we merged
  Hard Hat Workers into our main dataset, the model got worse (0.80 → 0.76) because Hard Hat Workers boxes cover the
  whole head including the face, while our main dataset boxes only the hard hat. Only merge datasets that draw boxes the
  same way.

**To agree on:** keep 960 for training and detection (or 640 if the Jetson can't keep up).

## 2. Do we need to clear the background after it detects all the people?

**Short answer:** no.

- The model needs the full picture. It was trained on real site photos with their backgrounds, and it also detects
  things that *are* the background: machinery, vehicles and safety cones.
- It finds hard hats, vests and masks directly, in the same pass as people, so there's no second step that would need a
  clean background.
- Removing the background would also cost time on the Jetson and could cut off parts of people, like a hard hat at
  the edge of a person's box.

**When cropping would make sense:** if we later want to say *which* person is missing their hard hat, we match each
hard hat / NO-Hardhat box to the person box it sits inside. That uses the boxes the model already gives us. It
doesn't need the background removed.

**Separate idea, if wanted:** blurring faces in saved snapshots and clips, for workers' privacy. That's about privacy,
not detection, and would happen after detection.

## 3. Detecting the smoking act itself (cigarette, pipe, vape, shisha), not just the cigarette

**Why:** the current model (`models/smoking.pt`, trained on CigDet) only knows cigarettes. On a pipe photo
(`smoking_0024.jpg`) it scored 0.31, below our 0.5 threshold, so it missed it. It can't detect vapes at all.

**Why not detect smoke on its own:** a construction site is full of things that look like smoke: dust, cement powder,
welding fumes, steam, engine exhaust, breath on cold mornings. A smoke detector would raise false alarms all day. Exhaled
smoke is also faint, see-through and gone in a second or two, so a camera several metres away often can't see it.
Most public "smoke" datasets are fire smoke, not smoke from someone's mouth.

**Proposed plan:**
1. The PPE model already gives a box for every person.
2. Crop each person's head and upper body and run a small second model on the crop: *smoking or not smoking*. Train it
   on people smoking cigarettes, pipes, vapes and shisha (with and without visible smoke), and on people who are *not*
   smoking but look similar: drinking, eating, on the phone, coughing, touching their face.
3. Alert only if it keeps happening over a few seconds. The rule engine's existing duration setting already does this.

Smoke near the mouth becomes one clue the model learns, not the only one. Keep `smoking.pt` running until the new model
beats it.

**Limits to expect:** distance is still the hard part. A head 10 m away is small in the frame. Expect it to work best
within a few metres, and test with our Arducam at 2, 5 and 8 m. We need a fair mix of cigarettes, pipes, vapes and
shisha in the training data, or it will miss the rare ones like the current model misses pipes.

### Datasets found (2026-10-21)

Not downloaded or checked yet. Roboflow pages couldn't be opened automatically, so the image counts and class
lists below come from search results and must be confirmed on each page. Roboflow downloads need an API key.

**For the "smoking / not smoking" model (whole picture of a person):**

| Dataset | What's in it | License | Link |
|---|---|---|---|
| Smoker Detection Dataset (Mendeley, 2022) | 1,120 images: 560 smoking, 560 not smoking. The "not smoking" photos were chosen to look similar (drinking water, coughing, inhaler, phone). Resized to 250×250. Same authors as CigDet. | Not confirmed, check the page | [data.mendeley.com/datasets/j45dj8bgfc](https://data.mendeley.com/datasets/j45dj8bgfc/1) |
| Smoking vs not-smoking (Mendeley, 2020) | 2,400 images: 1,200 per class. Same authors. | Not confirmed | [data.mendeley.com/datasets/7b52hhzs3r](https://data.mendeley.com/datasets/7b52hhzs3r/1) |
| smoking-detection (Roboflow, smoking-bycpp) | Box around the whole person, class "smoker". | CC BY 4.0 | [link](https://universe.roboflow.com/smoking-bycpp/smoking-detection-8fgr8) |

These two Mendeley sets are mostly cigarettes. We'd need to add pipe, vape and shisha photos ourselves (from the sets
below, or labelled by us).

**Datasets with vapes, pipes, shisha and smoke (object boxes):**

| Dataset | Classes (from search results) | Size | License | Link |
|---|---|---|---|---|
| vape-cigarette-detection-2 (stelar) | cigarette, vape | 1,149 images | Not confirmed | [link](https://universe.roboflow.com/stelar/vape-cigarette-detection-2) |
| Cigarette Vape Detection (telai) | cigarette, vape | Not confirmed | CC BY 4.0 | [link](https://universe.roboflow.com/telai/cigarette-vape-detection-xvtxe) |
| Cigarette Vape Detection (hugefissure) | cigarette, vape | Not confirmed | CC BY 4.0 | [link](https://universe.roboflow.com/hugefissure/cigarette-vape-detection-lagrc) |
| SmokeTrack | smoke, person, cigarette, smoking, vape | 860 images | CC BY 4.0 | [link](https://universe.roboflow.com/smoketrack/smoketrack-eldf7) |
| smoking (object-detection-vnf3r) | smoke, person, cigarette, vape | Not confirmed | CC BY 4.0 | [link](https://universe.roboflow.com/object-detection-vnf3r/smoking-qbqdv) |
| cigarette-detection (mi-privado) | smoke, person, cigarette, smoking, vape | Not confirmed | MIT | [link](https://universe.roboflow.com/mi-privado/cigarette-detection-iggcm) |
| Cigar-Pipe-Shisha-Classification | pipe, cigar, normal (classification, not boxes) | Not confirmed | CC BY 4.0 | [link](https://universe.roboflow.com/object-detection-trurj/cigar-pipe-shisha-classification) |
| hookah-detect | hookah | 138 images | Not confirmed | [link](https://universe.roboflow.com/denpetenevs-workspace/hookah-detect) |
| Hookah (sava) | hookah | Not confirmed | CC BY 4.0 | [link](https://universe.roboflow.com/sava/hookah) |
| New Smoke (vrunds-workspace) | smoke, pipe, new-smoke | Not confirmed | Not confirmed | [link](https://universe.roboflow.com/vrunds-workspace/new-smoke) |

**For video (if we later want to use movement, like the hand going to the mouth):** HMDB51 has a "smoke" action
class among its 51 actions ([link](https://cbmm.mit.edu/publications/large-video-database-human-motion-recognition)),
and "Coffee and Cigarettes" is a classic movie-based set with 141 smoking clips. Papers note that hand-to-mouth
alone isn't enough: some smokers keep their hand at their mouth while inhaling.

**Gaps:** no proper pipe dataset found (the one "pipe-project" listing is empty). Shisha sets are small. None of the
pages confirms that "smoke" means smoke breathed out by a person rather than fire smoke.

### What we built (2026-10-21)

**Three answers instead of two.** Each person's head-and-upper-body crop is labelled *smoking* (the item is at the
mouth, or smoke is coming out of the mouth), *holding* (has a cigarette or vape, not at the mouth) or *not smoking*.
Only *smoking* raises an alert. Keeping *holding* separate teaches the model that an item in the hand is not the act.

**Data** (`data/smoking_act2`, 13,590 crops): smoking 3,947, holding 1,564, not smoking 7,632. The not-smoking side
has look-alikes from Stanford 40 Actions (drinking, phoning, brushing teeth, blowing bubbles, make-up, texting,
taking photos), the Mendeley and cigar/pipe/shisha look-alikes, ordinary people, and 3,000 construction workers.
Mouth vs hand was decided automatically from the pose model's nose and eye points and the item boxes, then about
1,500 labels (all of the test set's smoking and holding crops, plus the doubtful training crops) were checked by eye.

**Results** (test set, every smoking / holding crop checked by eye, threshold 0.5):

| Model | Smokers found | "Smoking" answers that are right | Holding called smoking | False alarms |
|---|---|---|---|---|
| Old `smoking.pt` (cigarette detector) | missed the pipe and vape test photos | | | |
| YOLO11s, 224 px | 85.7% | 96.0% | 29% | 1.2% |
| **YOLO11m, 320 px** (`outputs/runs/smoking_act2_m320_clean`) | **88.5%** | **98.0%** | **26%** | **0.6%** |

Construction workers called smoking: 0%. Look-alikes: 0-10% depending on the kind (blowing bubbles is the worst).
Both test photos from 2026-10-21 are now right (pipe 1.00, vape exhale 0.58).

**Still weak:** about 1 in 4 people holding something away from their mouth is called smoking, mostly vapes. More
labelled "holding a vape" photos would help. Licence note: Stanford 40 is for research use; fine for the project,
but we must cite it and must not republish its images.

**Next steps:**
0. (2026-10-22) Put the YOLO11m model into the detector (crop each person, classify, alert on "smoking"), export
   it to TensorRT on the Jetson, then test with the Arducam at 2, 5 and 8 m. The old steps below are done.
1. Open the Roboflow pages and confirm image counts, classes and licenses. Pick 2-3 sets.
2. Look at ~50 photos from each: are they close-ups, or people at a distance like our camera?
3. Build the smoking / not-smoking set from the person crops, balanced across cigarette, pipe, vape and shisha.
4. Test against `smoking.pt` on the same photos, plus our own Arducam clips at 2, 5 and 8 m.
