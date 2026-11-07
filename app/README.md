# Pliny app

Browse and search the pipeline's results on phone, desktop or web. Same data and colours as
`data/06_graph/explorer.html`. Historical claims only, not medical advice.

- **Search**: any condition, symptom, plant or word, filtered by verdict.
- **Plants** and **Conditions**: every plant or condition, most documented first, with all its
  remedies, Pliny's words and the papers behind each verdict.
- **Assistant** (preview): a chat screen for the planned AI assistant connected to our evidence
  resolver. For now it answers with a keyword match on the local data; there is no backend.
- **About**: method, planned features (placeholders), team and sources.

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
