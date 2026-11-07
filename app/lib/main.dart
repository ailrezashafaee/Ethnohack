import 'package:flutter/material.dart';

import 'data.dart';
import 'screens/home_shell.dart';
import 'theme.dart';

void main() => runApp(const PlinyApp());

class PlinyApp extends StatefulWidget {
  const PlinyApp({super.key});

  @override
  State<PlinyApp> createState() => _PlinyAppState();
}

class _PlinyAppState extends State<PlinyApp> {
  final _catalog = Catalog.load();

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Was Pliny right?',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      home: FutureBuilder<Catalog>(
        future: _catalog,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Scaffold(
              body: Center(
                child: Text('Could not load the data: ${snapshot.error}'),
              ),
            );
          }
          final catalog = snapshot.data;
          if (catalog == null) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }
          return HomeShell(catalog: catalog);
        },
      ),
    );
  }
}
