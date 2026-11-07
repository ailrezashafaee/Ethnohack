import 'dart:convert';
import 'dart:math';

import 'package:flutter/services.dart';

enum Verdict {
  supported('supported', 'Supported', 'supported by a human study or review'),
  partlyStudied(
    'partly_studied',
    'Partly studied',
    'partly studied (animal or lab work)',
  ),
  contradicted(
    'contradicted',
    'Contradicted',
    'contradicted (no effect in humans)',
  ),
  notConfirmed(
    'not_confirmed',
    'Not confirmed',
    'papers exist, none tests this remedy',
  ),
  untested('untested', 'Untested', 'no paper on this plant and condition');

  const Verdict(this.key, this.label, this.description);

  final String key;
  final String label;
  final String description;

  static Verdict parse(String key) => values.firstWhere((v) => v.key == key);
}

class Plant {
  Plant.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      name = json['name'] as String,
      scientific = json['scientific'] as String? ?? '',
      status = json['status'] as String? ?? '';

  final String id;
  final String name;
  final String scientific;
  final String status;
}

class Condition {
  Condition.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      label = json['label'] as String,
      meshId = json['mesh_id'] as String? ?? '',
      category = json['category'] as String? ?? '';

  final String id;
  final String label;
  final String meshId;
  final String category;
}

class Claim {
  Claim.fromJson(Map<String, dynamic> json)
    : term = json['term'] as String? ?? '',
      quote = json['quote'] as String? ?? '',
      chapter = json['chapter'] as int,
      sentence = json['sentence'] as String? ?? '',
      source = json['source'] as String? ?? '',
      isHarm = json['type'] == 'harm';

  final String term;
  final String quote;
  final int chapter;
  final String sentence;
  final String source;
  final bool isHarm;
}

class Paper {
  Paper.fromJson(Map<String, dynamic> json)
    : id = '${json['id']}',
      title = json['title'] as String? ?? '',
      year = '${json['year'] ?? ''}',
      studyType = (json['study_type'] as String? ?? '').replaceAll('_', ' '),
      result = json['result'] as String? ?? '';

  final String id;
  final String title;
  final String year;
  final String studyType;
  final String result;

  Uri get link => RegExp(r'^\d+$').hasMatch(id)
      ? Uri.parse('https://pubmed.ncbi.nlm.nih.gov/$id/')
      : Uri.https('europepmc.org', '/search', {'query': id});
}

class Remedy {
  Remedy({
    required this.plant,
    required this.condition,
    required this.verdict,
    required this.claims,
    required this.papers,
  }) : _text = [
         plant.name,
         plant.scientific,
         condition.label,
         for (final claim in claims) ...[claim.term, claim.quote],
       ].join(' ').toLowerCase();

  final Plant plant;
  final Condition condition;
  final Verdict verdict;
  final List<Claim> claims;
  final List<Paper> papers;
  final String _text;

  bool matches(List<String> words) => words.every(_text.contains);

  bool mentions(String word) => _text.contains(word);
}

class Catalog {
  Catalog(this.plants, this.conditions, this.remedies) {
    for (final r in remedies) {
      _byPlant.putIfAbsent(r.plant, () => []).add(r);
      _byCondition.putIfAbsent(r.condition, () => []).add(r);
    }
    int claimsOf(List<Remedy>? rs) =>
        (rs ?? const []).fold(0, (n, r) => n + r.claims.length);
    for (final p in plants) {
      claimsPerPlant[p] = claimsOf(_byPlant[p]);
    }
    for (final c in conditions) {
      claimsPerCondition[c] = claimsOf(_byCondition[c]);
    }
    plants.sort((a, b) => claimsPerPlant[b]!.compareTo(claimsPerPlant[a]!));
    conditions.sort(
      (a, b) => claimsPerCondition[b]!.compareTo(claimsPerCondition[a]!),
    );
  }

  factory Catalog.fromJson(Map<String, dynamic> json) {
    final plants = {
      for (final p in json['plants'] as List)
        (p['id'] as String): Plant.fromJson(p),
    };
    final conditions = {
      for (final c in json['conditions'] as List)
        (c['id'] as String): Condition.fromJson(c),
    };
    final remedies = [
      for (final r in json['remedies'] as List)
        Remedy(
          plant: plants[r['plant']]!,
          condition: conditions[r['condition']]!,
          verdict: Verdict.parse(r['verdict'] as String),
          claims: [for (final c in r['claims'] as List) Claim.fromJson(c)],
          papers: [for (final p in r['papers'] as List) Paper.fromJson(p)],
        ),
    ]..sort(_byStrength);
    return Catalog(
      plants.values.toList(),
      conditions.values.toList(),
      remedies,
    );
  }

  static Future<Catalog> load() async => Catalog.fromJson(
    jsonDecode(await rootBundle.loadString('assets/graph.json')),
  );

  final List<Plant> plants;
  final List<Condition> conditions;
  final List<Remedy> remedies;
  final claimsPerPlant = <Plant, int>{};
  final claimsPerCondition = <Condition, int>{};
  final _byPlant = <Plant, List<Remedy>>{};
  final _byCondition = <Condition, List<Remedy>>{};

  List<Remedy> ofPlant(Plant plant) => _byPlant[plant] ?? const [];

  List<Remedy> ofCondition(Condition condition) =>
      _byCondition[condition] ?? const [];

  List<Remedy> search(String query) {
    final words = _words(query);
    if (words.isEmpty) return const [];
    return remedies.where((r) => r.matches(words)).toList();
  }

  List<Remedy> answer(String question, {int limit = 5}) {
    final words = _words(question).where((w) => !_stopWords.contains(w));
    final scored = [
      for (final r in remedies) (r, words.where(r.mentions).length),
    ]..removeWhere((e) => e.$2 == 0);
    if (scored.isEmpty) return const [];
    final best = scored.map((e) => e.$2).reduce(max);
    return [
      for (final (r, score) in scored)
        if (score == best) r,
    ].take(limit).toList();
  }

  static List<String> _words(String text) =>
      text.toLowerCase().split(RegExp(r'[^a-z0-9-]+'))
        ..removeWhere((w) => w.isEmpty);

  static const _stopWords = {
    'a',
    'an',
    'and',
    'are',
    'can',
    'do',
    'does',
    'did',
    'for',
    'from',
    'good',
    'help',
    'helps',
    'how',
    'i',
    'in',
    'is',
    'it',
    'me',
    'my',
    'of',
    'on',
    'or',
    'pliny',
    'remedy',
    'remedies',
    'right',
    'say',
    'said',
    'the',
    'to',
    'true',
    'use',
    'was',
    'what',
    'which',
    'with',
    'work',
    'works',
    'have',
    'has',
    'against',
    'cure',
    'cures',
    'treat',
    'treats',
    'about',
    'there',
    'any',
  };

  static int _byStrength(Remedy a, Remedy b) {
    final byVerdict = a.verdict.index.compareTo(b.verdict.index);
    return byVerdict != 0
        ? byVerdict
        : b.claims.length.compareTo(a.claims.length);
  }
}
