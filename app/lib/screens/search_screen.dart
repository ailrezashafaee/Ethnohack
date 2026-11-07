import 'package:flutter/material.dart';

import '../data.dart';
import '../theme.dart';
import '../widgets.dart';

const examples = ['toothache', 'headache', 'cough', 'sleep', 'garlic', 'snake'];

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.catalog});

  final Catalog catalog;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _query = TextEditingController();
  final _shown = Set<Verdict>.of(Verdict.values);

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  void _search(String text) {
    _query.text = text;
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final catalog = widget.catalog;
    final typed = _query.text.trim().isNotEmpty;
    final found = catalog.search(_query.text);
    final results = found.where((r) => _shown.contains(r.verdict)).toList();
    final counts = {
      for (final v in Verdict.values)
        v: found.where((r) => r.verdict == v).length,
    };

    return LayoutBuilder(
      builder: (context, constraints) {
        final side = sidePadding(constraints.maxWidth);
        return CustomScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          slivers: [
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                side,
                isCompact(context) ? 20 : 40,
                side,
                12,
              ),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const PageHeader(
                      title: 'Was Pliny right?',
                      lede:
                          'Search a condition, a symptom, a plant or any word. See what '
                          'Pliny prescribed in Natural History, Book 20, and what modern '
                          'papers say.',
                    ),
                    const SizedBox(height: 20),
                    TextField(
                      controller: _query,
                      textInputAction: TextInputAction.search,
                      onChanged: (_) => setState(() {}),
                      decoration: InputDecoration(
                        hintText: 'e.g. toothache, sleep, garlic',
                        prefixIcon: const Icon(Icons.search),
                        suffixIcon: _query.text.isEmpty
                            ? null
                            : IconButton(
                                tooltip: 'Clear',
                                icon: const Icon(Icons.close),
                                onPressed: () => _search(''),
                              ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (typed)
                      _Filters(
                        counts: counts,
                        shown: _shown,
                        onToggle: (v) => setState(
                          () => _shown.contains(v)
                              ? _shown.remove(v)
                              : _shown.add(v),
                        ),
                      )
                    else ...[
                      _Examples(onTap: _search),
                      const SizedBox(height: 28),
                      _Overview(catalog),
                    ],
                    const SizedBox(height: 12),
                    if (typed)
                      Text(
                        '${results.length} remedies',
                        style: TextStyle(color: palette.muted, fontSize: 13),
                      ),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: EdgeInsets.symmetric(horizontal: side),
              sliver: SliverList.separated(
                itemCount: results.length,
                separatorBuilder: (_, _) => const SizedBox(height: 8),
                itemBuilder: (context, i) => RemedyCard(results[i]),
              ),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(side, 24, side, 32),
              sliver: const SliverToBoxAdapter(child: Disclaimer()),
            ),
          ],
        );
      },
    );
  }
}

class _Overview extends StatelessWidget {
  const _Overview(this.catalog);

  final Catalog catalog;

  @override
  Widget build(BuildContext context) {
    final claims = catalog.remedies.fold(0, (n, r) => n + r.claims.length);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            _Stat(value: catalog.plants.length, label: 'plants'),
            _Stat(value: catalog.conditions.length, label: 'conditions'),
            _Stat(value: catalog.remedies.length, label: 'remedies'),
            _Stat(value: claims, label: 'claims in Pliny\'s words'),
          ],
        ),
        const SizedBox(height: 20),
        Text(
          'How the remedies hold up today',
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 10),
        VerdictBar(catalog.remedies),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.label});

  final int value;
  final String label;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return Container(
      width: 150,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: palette.panel,
        border: Border.all(color: palette.rule),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$value', style: serif(context, 30)),
          Text(label, style: TextStyle(color: palette.muted, fontSize: 13)),
        ],
      ),
    );
  }
}

class _Examples extends StatelessWidget {
  const _Examples({required this.onTap});

  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    runSpacing: 8,
    children: [
      for (final word in examples)
        ActionChip(label: Text(word), onPressed: () => onTap(word)),
    ],
  );
}

class _Filters extends StatelessWidget {
  const _Filters({
    required this.counts,
    required this.shown,
    required this.onToggle,
  });

  final Map<Verdict, int> counts;
  final Set<Verdict> shown;
  final ValueChanged<Verdict> onToggle;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final v in Verdict.values)
          FilterChip(
            avatar: CircleAvatar(
              backgroundColor: palette.verdict(v),
              radius: 6,
            ),
            label: Text('${v.label} (${counts[v]})'),
            selected: shown.contains(v),
            showCheckmark: false,
            onSelected: (_) => onToggle(v),
          ),
      ],
    );
  }
}
