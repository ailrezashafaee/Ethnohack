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
}
