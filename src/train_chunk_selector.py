import csv
import json
from collections import Counter
from pathlib import Path

from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, export_text


DATASET_PATH = Path("datasets/phase3/chunk_oracle_dataset.csv")
MODEL_OUTPUT = Path("results/phase3_interleaved/chunk_selector_tree.json")
REPORT_OUTPUT = Path("results/phase3_interleaved/chunk_selector_training_report.txt")


FEATURES = [
    "chunk_size",
    "original_size",
    "entropy",
    "text_ratio",
    "zero_ratio",
    "unique_byte_count",
]


def load_dataset():
    X = []
    y = []

    with open(DATASET_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            X.append([
                float(row["chunk_size"]),
                float(row["original_size"]),
                float(row["entropy"]),
                float(row["text_ratio"]),
                float(row["zero_ratio"]),
                float(row["unique_byte_count"]),
            ])
            y.append(row["best_compressor"])

    return X, y


def tree_to_dict(tree, feature_names, class_names):
    tree_ = tree.tree_

    def recurse(node):
        if tree_.feature[node] == -2:
            values = tree_.value[node][0]
            best_index = int(values.argmax())
            return {
                "type": "leaf",
                "class": class_names[best_index],
                "counts": {
                    class_names[i]: int(values[i])
                    for i in range(len(class_names))
                    if int(values[i]) > 0
                },
            }

        feature = feature_names[tree_.feature[node]]
        threshold = float(tree_.threshold[node])

        return {
            "type": "decision",
            "feature": feature,
            "threshold": threshold,
            "left_if_leq": recurse(tree_.children_left[node]),
            "right_if_gt": recurse(tree_.children_right[node]),
        }

    return recurse(0)


def main():
    X, y = load_dataset()

    print(f"Rows: {len(X)}")
    print("Labels:", dict(Counter(y)))

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    clf = DecisionTreeClassifier(
        max_depth=6,
        min_samples_leaf=10,
        random_state=42,
        class_weight="balanced",
    )

    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)

    report = classification_report(y_test, y_pred)
    matrix = confusion_matrix(y_test, y_pred, labels=clf.classes_)

    readable_tree = export_text(clf, feature_names=FEATURES)

    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    model_data = {
        "features": FEATURES,
        "classes": list(clf.classes_),
        "tree": tree_to_dict(clf, FEATURES, list(clf.classes_)),
    }

    with open(MODEL_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(model_data, f, indent=2)

    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write("Chunk Selector Training Report\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Rows: {len(X)}\n")
        f.write(f"Labels: {dict(Counter(y))}\n\n")
        f.write("Classification Report\n")
        f.write("-" * 80 + "\n")
        f.write(report)
        f.write("\n\nConfusion Matrix\n")
        f.write("-" * 80 + "\n")
        f.write("labels: " + ", ".join(clf.classes_) + "\n")
        for row in matrix:
            f.write(" ".join(str(int(x)) for x in row) + "\n")
        f.write("\n\nDecision Tree\n")
        f.write("-" * 80 + "\n")
        f.write(readable_tree)

    print(report)
    print(f"Saved model to {MODEL_OUTPUT}")
    print(f"Saved report to {REPORT_OUTPUT}")


if __name__ == "__main__":
    main()