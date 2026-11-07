import 'package:flutter/material.dart';

import '../theme.dart';
import '../widgets.dart';

const steps = [
  (
    'Text',
    'Book 20 of Pliny\'s Natural History (1855 translation), split into chapters and sentences.',
  ),
  (
    'Claims',
    'A local language model extracts every remedy with Pliny\'s exact words.',
  ),
  (
    'Plants',
    'Plant names are matched to modern scientific names (World Flora Online).',
  ),
  ('Conditions', 'Conditions are mapped to modern medical terms (MeSH).'),
  (
    'Evidence',
    'Each plant and condition pair is searched in Europe PMC and the top papers are read.',
  ),
  (
    'Verdict',
    'Supported, partly studied, contradicted, not confirmed or untested.',
  ),
];

const plans = [
  (
    Icons.forum_outlined,
    'AI assistant',
    'Ask in plain words about a condition or a remedy you know. A language model '
        'connected to our evidence resolver finds the claim and explains the verdict.',
  ),
  (
    Icons.menu_book_outlined,
    'More sources',
    'Books 21 to 27 of the Natural History, then other historical herbals and '
        'traditional medicine texts.',
  ),
  (
    Icons.update,
    'Live evidence',
    'Verdicts are checked again as new papers appear, with a history of changes.',
  ),
  (
    Icons.science_outlined,
    'From plant to molecule',
    'Link each plant to its known compounds and their biological targets, to find '
        'leads worth testing.',
  ),
  (
    Icons.bookmark_border,
    'Accounts and saved searches',
    'Researchers, clinicians and curious readers keep their searches and get '
        'notified when a verdict changes.',
  ),
  (
    Icons.api,
    'Open API',
    'The same data for other apps and research tools, with full citations.',
  ),
];

const team = [
  ('Alireza Shafaee', 'Developer · M.Sc. student, Computer Science'),
  ('Alireza Ghasemi', 'M.Sc. student, Life Science Informatics'),
];

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final side = sidePadding(constraints.maxWidth);
        final cardWidth = isCompact(context) ? double.infinity : 390.0;
        return ListView(
          padding: EdgeInsets.fromLTRB(
            side,
            isCompact(context) ? 20 : 40,
            side,
            32,
          ),
          children: [
            const PageHeader(
              title: 'About',
              lede:
                  'An auditable path from ancient remedy claims to modern evidence. '
                  'Built for EthnoHack 2026, Track 1: Traditional Knowledge Mining.',
            ),
            const _Heading('How it works'),
            for (final (i, (name, text)) in steps.indexed)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    CircleAvatar(
                      radius: 13,
                      backgroundColor: palette.herb,
                      child: Text(
                        '${i + 1}',
                        style: TextStyle(
                          color: palette.panel,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: '$name. ',
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            TextSpan(text: text),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            const _Heading('Coming next'),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                for (final (icon, title, text) in plans)
                  SizedBox(
                    width: cardWidth,
                    child: _PlanCard(icon: icon, title: title, text: text),
                  ),
              ],
            ),
            const _Heading('Team'),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                for (final (name, role) in team)
                  SizedBox(
                    width: cardWidth,
                    child: _PersonCard(name: name, role: role),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'University of Bonn',
              style: TextStyle(color: palette.muted, fontSize: 13.5),
            ),
            const _Heading('Sources'),
            Text(
              'Pliny the Elder, Natural History, tr. J. Bostock and H. T. Riley (1855), '
              'Perseus Digital Library, CC BY-SA 3.0 US. Plant names: World Flora '
              'Online. Conditions: MeSH (U.S. National Library of Medicine). '
              'Papers: Europe PMC.',
              style: TextStyle(color: palette.muted, fontSize: 13.5),
            ),
            const SizedBox(height: 24),
            const Divider(),
            const SizedBox(height: 10),
            const Disclaimer(),
          ],
        );
      },
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 28, bottom: 12),
    child: Text(text, style: serif(context, 26)),
  );
}

class _PlanCard extends StatelessWidget {
  const _PlanCard({
    required this.icon,
    required this.title,
    required this.text,
  });

  final IconData icon;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: palette.herb),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                    ),
                  ),
                ),
                const Tag(text: 'PLANNED'),
              ],
            ),
            const SizedBox(height: 8),
            Text(text, style: TextStyle(color: palette.muted, fontSize: 13.5)),
          ],
        ),
      ),
    );
  }
}

class _PersonCard extends StatelessWidget {
  const _PersonCard({required this.name, required this.role});

  final String name;
  final String role;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final initials = name.split(' ').map((w) => w[0]).join();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            CircleAvatar(
              radius: 22,
              backgroundColor: palette.herb,
              child: Text(
                initials,
                style: TextStyle(
                  color: palette.panel,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: serif(context, 21)),
                  Text(
                    role,
                    style: TextStyle(color: palette.muted, fontSize: 13.5),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
