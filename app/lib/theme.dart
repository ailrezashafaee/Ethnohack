import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'data.dart';

class Palette {
  const Palette({
    required this.paper,
    required this.panel,
    required this.ink,
    required this.muted,
    required this.rule,
    required this.herb,
    required this.unconfirmed,
    required this.untested,
  });

  final Color paper;
  final Color panel;
  final Color ink;
  final Color muted;
  final Color rule;
  final Color herb;
  final Color unconfirmed;
  final Color untested;

  static const supported = Color(0xFF2F7D4F);
  static const partly = Color(0xFFB8892A);
  static const contradicted = Color(0xFFA33A3A);

  static const light = Palette(
    paper: Color(0xFFE8ECE4),
    panel: Color(0xFFF3F5F0),
    ink: Color(0xFF1F2A24),
    muted: Color(0xFF5D6A62),
    rule: Color(0xFFC9D1C6),
    herb: Color(0xFF3F5A3A),
    unconfirmed: Color(0xFFC4B896),
    untested: Color(0xFF8E979B),
  );

  static const dark = Palette(
    paper: Color(0xFF171D19),
    panel: Color(0xFF1F2721),
    ink: Color(0xFFE3E8E1),
    muted: Color(0xFFA3AFA6),
    rule: Color(0xFF344038),
    herb: Color(0xFF9CBF8F),
    unconfirmed: Color(0xFF8C835F),
    untested: Color(0xFF7B8589),
  );

  static Palette of(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark ? dark : light;

  Color verdict(Verdict verdict) => switch (verdict) {
    Verdict.supported => supported,
    Verdict.partlyStudied => partly,
    Verdict.contradicted => contradicted,
    Verdict.notConfirmed => unconfirmed,
    Verdict.untested => untested,
  };
}

TextStyle serif(BuildContext context, double size, {bool italic = false}) =>
    GoogleFonts.cormorantGaramond(
      fontSize: size,
      fontWeight: italic ? FontWeight.w500 : FontWeight.w600,
      fontStyle: italic ? FontStyle.italic : FontStyle.normal,
      color: Palette.of(context).ink,
      height: 1.15,
    );

ThemeData buildTheme(Brightness brightness) {
  final palette = brightness == Brightness.dark ? Palette.dark : Palette.light;
  final base = ThemeData(
    brightness: brightness,
    colorScheme: ColorScheme.fromSeed(
      seedColor: palette.herb,
      brightness: brightness,
      primary: palette.herb,
      surface: palette.paper,
      onSurface: palette.ink,
    ),
    scaffoldBackgroundColor: palette.paper,
  );
  return base.copyWith(
    textTheme: GoogleFonts.sourceSans3TextTheme(
      base.textTheme,
    ).apply(bodyColor: palette.ink, displayColor: palette.ink),
    appBarTheme: AppBarTheme(
      backgroundColor: palette.panel,
      foregroundColor: palette.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      shape: Border(bottom: BorderSide(color: palette.rule)),
    ),
    cardTheme: CardThemeData(
      color: palette.panel,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(6),
        side: BorderSide(color: palette.rule),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: palette.panel,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: BorderSide(color: palette.rule),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: BorderSide(color: palette.rule),
      ),
    ),
    dividerTheme: DividerThemeData(color: palette.rule, space: 1),
  );
}
