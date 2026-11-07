import 'dart:math';

import 'package:flutter/material.dart';

import 'data.dart';
import 'screens/remedy_screen.dart';
import 'theme.dart';

const maxContentWidth = 820.0;

bool isCompact(BuildContext context) => MediaQuery.sizeOf(context).width < 600;

double sidePadding(double width) => max(16.0, (width - maxContentWidth) / 2);

class Centered extends StatelessWidget {
  const Centered({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: maxContentWidth),
      child: child,
    ),
  );
}

class PageHeader extends StatelessWidget {
  const PageHeader({super.key, required this.title, this.lede, this.badge});

  final String title;
  final String? lede;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (badge != null) ...[
          Tag(text: badge!),
          const SizedBox(height: 10),
        ],
        Text(title, style: serif(context, isCompact(context) ? 32 : 40)),
        if (lede != null) ...[
          const SizedBox(height: 6),
          Text(lede!, style: TextStyle(color: palette.muted, fontSize: 15)),
        ],
      ],
    );
  }
}

class Tag extends StatelessWidget {
  const Tag({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.all(color: palette.herb),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        child: Text(
          text,
          style: TextStyle(
            color: palette.herb,
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.4,
          ),
        ),
      ),
    );
  }
}

class VerdictPill extends StatelessWidget {
  const VerdictPill(this.verdict, {super.key, this.long = false});

  final Verdict verdict;
  final bool long;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: Palette.of(context).verdict(verdict),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      child: Text(
        long ? verdict.description : verdict.label,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w600,
          fontSize: 13,
        ),
      ),
    ),
  );
}

class VerdictBar extends StatelessWidget {
  const VerdictBar(this.remedies, {super.key});

  final List<Remedy> remedies;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final counts = {
      for (final v in Verdict.values)
        v: remedies.where((r) => r.verdict == v).length,
    }..removeWhere((_, n) => n == 0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: SizedBox(
            height: 10,
            child: Row(
              children: [
                for (final MapEntry(key: v, value: n) in counts.entries)
                  Expanded(
                    flex: n,
                    child: ColoredBox(color: palette.verdict(v)),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 14,
          runSpacing: 4,
          children: [
            for (final MapEntry(key: v, value: n) in counts.entries)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircleAvatar(backgroundColor: palette.verdict(v), radius: 5),
                  const SizedBox(width: 6),
                  Text(
                    '${v.label} $n',
                    style: TextStyle(fontSize: 13, color: palette.muted),
                  ),
                ],
              ),
          ],
        ),
      ],
    );
  }
}

class RemedyCard extends StatelessWidget {
  const RemedyCard(this.remedy, {super.key});

  final Remedy remedy;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final claims = remedy.claims.length;
    final papers = remedy.papers.length;
    final details = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${remedy.plant.name} → ${remedy.condition.label}',
          style: serif(context, 21),
        ),
        if (remedy.plant.scientific.isNotEmpty)
          Text(remedy.plant.scientific, style: serif(context, 16, italic: true)),
        const SizedBox(height: 4),
        Text(
          '$claims ${claims == 1 ? 'claim' : 'claims'} · '
          '$papers ${papers == 1 ? 'paper' : 'papers'}',
          style: TextStyle(color: palette.muted, fontSize: 13),
        ),
      ],
    );
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.of(
          context,
        ).push(MaterialPageRoute(builder: (_) => RemedyScreen(remedy: remedy))),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: isCompact(context)
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    details,
                    const SizedBox(height: 8),
                    VerdictPill(remedy.verdict),
                  ],
                )
              : Row(
                  children: [
                    Expanded(child: details),
                    const SizedBox(width: 12),
                    VerdictPill(remedy.verdict),
                  ],
                ),
        ),
      ),
    );
  }
}

class Disclaimer extends StatelessWidget {
  const Disclaimer({super.key});

  @override
  Widget build(BuildContext context) => Text(
    'Historical claims, not medical advice. A verdict describes what the modern '
    'literature found in an automated search, not whether a remedy works or is safe. '
    'For any health concern, see a doctor.',
    style: TextStyle(fontSize: 12.5, color: Palette.of(context).muted),
  );
}
