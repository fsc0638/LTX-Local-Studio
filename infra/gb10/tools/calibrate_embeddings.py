"""Calibrate similarity thresholds for the Consistency (CJ) and Style (SJ) judges.

Layout:  ROOT/<character>/*.png|jpg   (>= 2 images per character, >= 2 characters)
Same-identity pairs come from inside one folder, different-identity pairs from across folders.
For each metric the report gives the same/different distributions, the threshold at target
false-positive rates, and the equal-error-rate point. Run inside the vision venv:

  /opt/studio/venvs/vision/bin/python calibrate_embeddings.py --root /path/to/calibration --out report.json
"""
import argparse
import itertools
import json
import pathlib

import numpy as np
import torch
from PIL import Image

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def load_images(root):
    images = []
    for folder in sorted(p for p in pathlib.Path(root).iterdir() if p.is_dir()):
        files = sorted(f for f in folder.iterdir() if f.suffix.lower() in EXTENSIONS)
        if len(files) < 2:
            print(f"skip {folder.name}: needs >= 2 images")
            continue
        images.extend((folder.name, f, Image.open(f).convert("RGB")) for f in files)
    characters = {name for name, _, _ in images}
    if len(characters) < 2:
        raise SystemExit("need >= 2 character folders with >= 2 images each")
    return images


def unit(vec):
    vec = vec.detach().float().cpu().numpy().reshape(-1)
    return vec / (np.linalg.norm(vec) + 1e-8)


def face_embedder(device):
    from facenet_pytorch import MTCNN, InceptionResnetV1
    detector = MTCNN(image_size=160, margin=20, keep_all=False, device=device)
    net = InceptionResnetV1(pretrained="vggface2").eval().to(device)

    def embed(image):
        face = detector(image)
        if face is None:
            return None
        with torch.no_grad():
            return unit(net(face.unsqueeze(0).to(device)))
    return embed


def dino_embedder(device):
    from transformers import AutoImageProcessor, AutoModel
    processor = AutoImageProcessor.from_pretrained("facebook/dinov2-large")
    model = AutoModel.from_pretrained("facebook/dinov2-large").eval().to(device)

    def embed(image):
        with torch.no_grad():
            inputs = processor(images=image, return_tensors="pt").to(device)
            return unit(model(**inputs).pooler_output)
    return embed


def clip_embedder(device):
    import open_clip
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-L-14", pretrained="openai", device=device)
    model.eval()

    def embed(image):
        with torch.no_grad():
            return unit(model.encode_image(preprocess(image).unsqueeze(0).to(device)))
    return embed


def lab_mean(image):
    from skimage import color
    return color.rgb2lab(np.asarray(image.resize((256, 256))) / 255.0).reshape(-1, 3).mean(axis=0)


def delta_e(lab_a, lab_b):
    from skimage import color
    return float(color.deltaE_ciede2000(lab_a.reshape(1, 1, 3), lab_b.reshape(1, 1, 3))[0, 0])


def summarize(name, same, diff, higher_is_similar, fprs=(0.01, 0.05)):
    same, diff = np.asarray(same, dtype=float), np.asarray(diff, dtype=float)
    if same.size == 0 or diff.size == 0:
        return {"metric": name, "note": "not enough pairs"}
    sign = 1.0 if higher_is_similar else -1.0
    s, d = sign * same, sign * diff
    report = {"metric": name, "higher_is_similar": higher_is_similar,
              "same": {"n": int(s.size), "mean": float(same.mean()), "std": float(same.std()),
                       "worst": float(same.min() if higher_is_similar else same.max())},
              "different": {"n": int(d.size), "mean": float(diff.mean()), "std": float(diff.std()),
                            "closest": float(diff.max() if higher_is_similar else diff.min())},
              "thresholds": {}}
    for fpr in fprs:
        threshold = float(np.quantile(d, 1.0 - fpr))
        tpr = float((s >= threshold).mean())
        report["thresholds"][f"fpr_{int(fpr * 100):02d}"] = {"threshold": sign * threshold, "tpr": tpr}
    grid = np.unique(np.concatenate([s, d]))
    best = min(grid, key=lambda t: abs((s < t).mean() - (d >= t).mean()))
    report["thresholds"]["eer"] = {"threshold": sign * float(best),
                                   "fnr": float((s < best).mean()), "fpr": float((d >= best).mean())}
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", default="calibration_report.json")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    images = load_images(args.root)
    embedders = {"face_facenet": face_embedder(args.device), "dinov2_large": dino_embedder(args.device),
                 "clip_vit_l14": clip_embedder(args.device)}
    vectors = {name: [] for name in embedders}
    labs = []
    missing_faces = []
    for character, path, image in images:
        for name, embed in embedders.items():
            vectors[name].append(embed(image))
        labs.append(lab_mean(image))
        if vectors["face_facenet"][-1] is None:
            missing_faces.append(str(path))

    labels = [character for character, _, _ in images]
    reports = []
    for name, vecs in vectors.items():
        same, diff = [], []
        for i, j in itertools.combinations(range(len(images)), 2):
            if vecs[i] is None or vecs[j] is None:
                continue
            (same if labels[i] == labels[j] else diff).append(float(np.dot(vecs[i], vecs[j])))
        reports.append(summarize(name, same, diff, higher_is_similar=True))
    same, diff = [], []
    for i, j in itertools.combinations(range(len(images)), 2):
        (same if labels[i] == labels[j] else diff).append(delta_e(labs[i], labs[j]))
    reports.append(summarize("lab_mean_delta_e", same, diff, higher_is_similar=False))

    for report in reports:
        if "note" in report:
            print(f"{report['metric']}: {report['note']}")
            continue
        t = report["thresholds"]
        print(f"{report['metric']:>18}  same {report['same']['mean']:.3f}±{report['same']['std']:.3f} "
              f"(worst {report['same']['worst']:.3f})  diff {report['different']['mean']:.3f}±{report['different']['std']:.3f} "
              f"(closest {report['different']['closest']:.3f})  thr@fpr1% {t['fpr_01']['threshold']:.3f} "
              f"(tpr {t['fpr_01']['tpr']:.2f})  thr@fpr5% {t['fpr_05']['threshold']:.3f} (tpr {t['fpr_05']['tpr']:.2f})  "
              f"eer {t['eer']['threshold']:.3f}")
    if missing_faces:
        print(f"no face detected in {len(missing_faces)} images (excluded from face metric):")
        for path in missing_faces:
            print("  ", path)
    payload = {"root": str(pathlib.Path(args.root).resolve()), "images": len(images),
               "characters": sorted(set(labels)), "missing_faces": missing_faces, "metrics": reports}
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("report ->", args.out)


if __name__ == "__main__":
    main()
