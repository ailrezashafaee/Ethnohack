import 'package:flutter/material.dart';

import '../data.dart';
import '../theme.dart';
import '../widgets.dart';
import 'group_screen.dart';

const plantSources = {
  'footnote': 'named in the 1855 footnotes',
  'footnote+llm': 'footnote and AI model agree',
  'manual': 'decided by the team',
  'llm': 'identified by the AI model',
  'disputed': 'footnote and AI model disagree',
};

class Entry {
  const Entry({
    required this.title,
    required this.subtitle,
    required this.claims,
    required this.remedies,
    required this.open,
  });

  final String title;
  final String subtitle;
  final int claims;
  final List<Remedy> remedies;
  final WidgetBuilder open;
}

class BrowseScreen extends StatefulWidget {
  const BrowseScreen({
    super.key,
    required this.title,
    required this.lede,
    required this.hint,
    required this.entries,
  });

  factory BrowseScreen.plants(Catalog catalog) => BrowseScreen(
    title: 'Plants',
    lede:
        'Every plant Pliny names in Book 20, matched to its modern scientific name. '
        'Most documented first.',
    hint: 'Filter plants, e.g. mint or Mentha',
    entries: [
      for (final p in catalog.plants)
        Entry(
          title: p.name,
          subtitle: p.scientific,
          claims: catalog.claimsPerPlant[p]!,
          remedies: catalog.ofPlant(p),
          open: (_) => GroupScreen(
            title: p.name,
            subtitle: p.scientific,
            facts: [
              if (plantSources[p.status] != null)
                'Identification: ${plantSources[p.status]}',
            ],
            remedies: catalog.ofPlant(p),
          ),
        ),
    ],
  );

  factory BrowseScreen.conditions(Catalog catalog) => BrowseScreen(
    title: 'Conditions',
    lede:
        'Every condition Pliny treats, mapped to a modern medical term (MeSH). '
        'Most documented first.',
    hint: 'Filter conditions, e.g. cough or fever',
    entries: [
      for (final c in catalog.conditions)
        Entry(
          title: c.label,
          subtitle: c.category.replaceAll('_', ' '),
          claims: catalog.claimsPerCondition[c]!,
          remedies: catalog.ofCondition(c),
          open: (_) => GroupScreen(
            title: c.label,
            subtitle: c.category.replaceAll('_', ' '),
            facts: [if (c.meshId.isNotEmpty) 'MeSH descriptor: ${c.meshId}'],
            remedies: catalog.ofCondition(c),
          ),
        ),
    ],
  );

  final String title;
  final String lede;
  final String hint;
  final List<Entry> entries;

  @override
  State<BrowseScreen> createState() => _BrowseScreenState();
}

class _BrowseScreenState extends State<BrowseScreen> {
  String _filter = '';

  @override
  Widget build(BuildContext context) {
    final q = _filter.trim().toLowerCase();
    final shown = q.isEmpty
        ? widget.entries
        : widget.entries
              .where(
                (e) =>
                    e.title.toLowerCase().contains(q) ||
                    e.subtitle.toLowerCase().contains(q),
              )
              .toList();

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
                16,
              ),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    PageHeader(title: widget.title, lede: widget.lede),
                    const SizedBox(height: 20),
                    TextField(
                      onChanged: (v) => setState(() => _filter = v),
                      decoration: InputDecoration(
                        hintText: widget.hint,
                        prefixIcon: const Icon(Icons.filter_list),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      '${shown.length} of ${widget.entries.length}',
                      style: TextStyle(
                        color: Palette.of(context).muted,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(side, 0, side, 32),
              sliver: SliverList.separated(
                itemCount: shown.length,
                separatorBuilder: (_, _) => const SizedBox(height: 8),
                itemBuilder: (context, i) => _EntryCard(shown[i]),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _EntryCard extends StatelessWidget {
  const _EntryCard(this.entry);

  final Entry entry;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final n = entry.remedies.length;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () =>
            Navigator.of(context).push(MaterialPageRoute(builder: entry.open)),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: Text(entry.title, style: serif(context, 22)),
                  ),
                  Text(
                    '${entry.claims} claims · $n ${n == 1 ? 'remedy' : 'remedies'}',
                    style: TextStyle(color: palette.muted, fontSize: 13),
                  ),
                ],
              ),
              if (entry.subtitle.isNotEmpty)
                Text(entry.subtitle, style: serif(context, 16, italic: true)),
              const SizedBox(height: 10),
              _MiniBar(entry.remedies),
            ],
          ),
        ),
      ),
    );
  }
}

class _MiniBar extends StatelessWidget {
  const _MiniBar(this.remedies);

  final List<Remedy> remedies;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return ClipRRect(
      borderRadius: BorderRadius.circular(3),
      child: SizedBox(
        height: 6,
        child: Row(
          children: [
            for (final v in Verdict.values)
              if (remedies.any((r) => r.verdict == v))
                Expanded(
                  flex: remedies.where((r) => r.verdict == v).length,
                  child: ColoredBox(color: palette.verdict(v)),
                ),
          ],
        ),
      ),
    );
  }
}
