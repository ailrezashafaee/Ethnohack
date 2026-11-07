import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:pliny_app/data.dart';

void main() {
  final catalog = Catalog.fromJson(
    jsonDecode(File('assets/graph.json').readAsStringSync()),
  );

  test('loads every remedy', () {
    expect(catalog.remedies, hasLength(1332));
  });

  test('finds toothache remedies, strongest verdict first', () {
    final results = catalog.search('Toothache');
    expect(
      results.where((r) => r.condition.label == 'Toothache'),
      hasLength(13),
    );
    expect(results.first.verdict, Verdict.partlyStudied);
  });

  test('needs every word to match', () {
    final results = catalog.search('garlic toothache');
    expect(results, isNotEmpty);
    expect(results.every((r) => r.plant.name == 'garlic'), isTrue);
  });

  test('empty query finds nothing', () {
    expect(catalog.search('   '), isEmpty);
  });

  test('groups remedies by plant and by condition', () {
    final garlic = catalog.plants.firstWhere((p) => p.name == 'garlic');
    expect(catalog.ofPlant(garlic), hasLength(44));
    final toothache = catalog.conditions.firstWhere(
      (c) => c.label == 'Toothache',
    );
    expect(catalog.ofCondition(toothache), hasLength(13));
    expect(
      catalog.claimsPerPlant[catalog.plants.first]!,
      greaterThanOrEqualTo(catalog.claimsPerPlant[catalog.plants.last]!),
    );
  });

  test('assistant preview answers a question in plain words', () {
    final answer = catalog.answer('Was garlic good for toothache?');
    expect(answer, isNotEmpty);
    expect(
      answer.every(
        (r) => r.plant.name == 'garlic' && r.condition.label == 'Toothache',
      ),
      isTrue,
    );
    expect(catalog.answer('what about it?'), isEmpty);
  });
}
