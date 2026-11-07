import 'package:flutter/material.dart';

import '../data.dart';
import '../theme.dart';
import 'about_screen.dart';
import 'assistant_screen.dart';
import 'browse_screen.dart';
import 'search_screen.dart';

const _destinations = [
  (Icons.search, Icons.search, 'Search'),
  (Icons.eco_outlined, Icons.eco, 'Plants'),
  (Icons.healing_outlined, Icons.healing, 'Conditions'),
  (Icons.forum_outlined, Icons.forum, 'Assistant'),
  (Icons.info_outline, Icons.info, 'About'),
];

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.catalog});

  final Catalog catalog;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  late final _pages = [
    SearchScreen(catalog: widget.catalog),
    BrowseScreen.plants(widget.catalog),
    BrowseScreen.conditions(widget.catalog),
    AssistantScreen(catalog: widget.catalog),
    const AboutScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final wide = MediaQuery.sizeOf(context).width >= 800;
    final body = IndexedStack(index: _index, children: _pages);
    void select(int i) => setState(() => _index = i);

    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            NavigationRail(
              backgroundColor: palette.panel,
              selectedIndex: _index,
              onDestinationSelected: select,
              labelType: NavigationRailLabelType.all,
              leading: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Icon(Icons.local_florist, color: palette.herb, size: 30),
              ),
              destinations: [
                for (final (icon, selected, label) in _destinations)
                  NavigationRailDestination(
                    icon: Icon(icon),
                    selectedIcon: Icon(selected),
                    label: Text(label),
                  ),
              ],
            ),
            VerticalDivider(width: 1, color: palette.rule),
            Expanded(child: SafeArea(child: body)),
          ],
        ),
      );
    }
    return Scaffold(
      body: SafeArea(bottom: false, child: body),
      bottomNavigationBar: NavigationBar(
        backgroundColor: palette.panel,
        selectedIndex: _index,
        onDestinationSelected: select,
        destinations: [
          for (final (icon, selected, label) in _destinations)
            NavigationDestination(
              icon: Icon(icon),
              selectedIcon: Icon(selected),
              label: label,
            ),
        ],
      ),
    );
  }
}
