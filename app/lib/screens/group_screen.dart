import 'package:flutter/material.dart';

import '../data.dart';
import '../theme.dart';
import '../widgets.dart';

class GroupScreen extends StatelessWidget {
  const GroupScreen({
    super.key,
    required this.title,
    required this.subtitle,
    required this.facts,
    required this.remedies,
  });

  final String title;
  final String subtitle;
  final List<String> facts;
  final List<Remedy> remedies;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final claims = remedies.fold(0, (n, r) => n + r.claims.length);
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: SafeArea(
        top: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final side = sidePadding(constraints.maxWidth);
            return CustomScrollView(
              slivers: [
                SliverPadding(
                  padding: EdgeInsets.fromLTRB(side, 24, side, 16),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: serif(context, isCompact(context) ? 30 : 36),
                        ),
                        if (subtitle.isNotEmpty)
                          Text(
                            subtitle,
                            style: serif(
                              context,
                              19,
                              italic: true,
                            ).copyWith(color: palette.muted),
                          ),
                        const SizedBox(height: 8),
                        for (final fact in facts)
                          Text(
                            fact,
                            style: TextStyle(
                              color: palette.muted,
                              fontSize: 13,
                            ),
                          ),
                        const SizedBox(height: 16),
                        Text(
                          '${remedies.length} remedies from $claims claims',
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 10),
                        VerdictBar(remedies),
                      ],
                    ),
                  ),
                ),
                SliverPadding(
                  padding: EdgeInsets.symmetric(horizontal: side),
                  sliver: SliverList.separated(
                    itemCount: remedies.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder: (context, i) => RemedyCard(remedies[i]),
                  ),
                ),
                SliverPadding(
                  padding: EdgeInsets.fromLTRB(side, 24, side, 32),
                  sliver: const SliverToBoxAdapter(child: Disclaimer()),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}
