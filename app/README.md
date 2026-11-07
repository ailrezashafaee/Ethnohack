# Pliny app

A simple search app over the pipeline's results: type a condition, symptom, plant or any word and
see what Pliny prescribed in *Natural History*, Book 20, the verdict from the modern literature,
his own words and the papers behind it. Same data and colours as `data/06_graph/explorer.html`.

Historical claims only, not medical advice.

## Run

```bash
cd app
flutter pub get
flutter run -d chrome      # or: macos, an iOS simulator, an Android phone
```

## Data

`assets/graph.json` is a copy of `data/06_graph/graph.json`. After rerunning stage 6, copy it again:

```bash
cp ../data/06_graph/graph.json assets/graph.json
```

## Check

```bash
flutter analyze
flutter test
```
