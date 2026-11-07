import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data.dart';
import '../theme.dart';
import '../widgets.dart';

class RemedyScreen extends StatelessWidget {
  const RemedyScreen({super.key, required this.remedy});

  final Remedy remedy;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final plant = remedy.plant;
    return Scaffold(
      appBar: AppBar(title: Text('${plant.name} → ${remedy.condition.label}')),
      body: SafeArea(
        top: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 24, 16, 32),
          child: Centered(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${plant.name} → ${remedy.condition.label}',
                  style: serif(context, isCompact(context) ? 26 : 30),
                ),
                if (plant.scientific.isNotEmpty)
                  Text(
                    '${plant.scientific}'
                    '${plant.status.isEmpty ? '' : ' — plant identified via ${plant.status}'}',
                    style: serif(
                      context,
                      18,
                      italic: true,
                    ).copyWith(color: palette.muted),
                  ),
                const SizedBox(height: 14),
                VerdictPill(remedy.verdict, long: true),
                const _Heading('What Pliny wrote'),
                for (final claim in remedy.claims) _Quote(claim),
                const _Heading('Modern papers that test it'),
                if (remedy.papers.isEmpty)
                  Text(
                    'No paper found that tests this plant for this condition.',
                    style: TextStyle(color: palette.muted),
                  )
                else
                  for (final paper in remedy.papers) _PaperTile(paper),
                const SizedBox(height: 24),
                const Divider(),
                const SizedBox(height: 10),
                const Disclaimer(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 24, bottom: 8),
    child: Text(
      text,
      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
    ),
  );
}

class _Quote extends StatelessWidget {
  const _Quote(this.claim);

  final Claim claim;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.only(left: 12),
      decoration: BoxDecoration(
        border: Border(left: BorderSide(color: palette.rule, width: 3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SelectableText(
            '“${claim.quote}”',
            style: serif(context, 18, italic: true).copyWith(height: 1.4),
          ),
          const SizedBox(height: 2),
          Text(
            'for “${claim.term}”${claim.isHarm ? ' (harm claim)' : ''} — '
            '${claim.source}, Book 20, chapter ${claim.chapter}, sentence ${claim.sentence}',
            style: TextStyle(fontSize: 13, color: palette.muted),
          ),
        ],
      ),
    );
  }
}

class _PaperTile extends StatelessWidget {
  const _PaperTile(this.paper);

  final Paper paper;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final meta = [
      paper.year,
      paper.studyType,
      if (paper.result.isNotEmpty) 'result: ${paper.result}',
    ].where((s) => s.isNotEmpty).join(', ');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: InkWell(
        onTap: () => launchUrl(paper.link),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              paper.title,
              style: TextStyle(
                color: palette.herb,
                decoration: TextDecoration.underline,
                decorationColor: palette.herb,
              ),
            ),
            Text(meta, style: TextStyle(fontSize: 12.5, color: palette.muted)),
          ],
        ),
      ),
    );
  }
}
