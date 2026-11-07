import 'package:flutter/material.dart';

import '../data.dart';
import '../theme.dart';
import '../widgets.dart';

const suggestions = [
  'Was garlic good for toothache?',
  'What did Pliny use for a cough?',
  'Is mint good for headaches?',
  'Remedies for snake bites',
];

class _Message {
  const _Message.user(this.text) : fromUser = true, remedies = const [];
  const _Message.assistant(this.text, [this.remedies = const []])
    : fromUser = false;

  final bool fromUser;
  final String text;
  final List<Remedy> remedies;
}

class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key, required this.catalog});

  final Catalog catalog;

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <_Message>[
    const _Message.assistant(
      'Ask about a condition, a symptom, a plant or a remedy you have in mind. '
      'I will show what Pliny claimed and what modern papers found.',
    ),
  ];

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _send(String text) {
    final question = text.trim();
    if (question.isEmpty) return;
    final found = widget.catalog.answer(question);
    setState(() {
      _messages
        ..add(_Message.user(question))
        ..add(
          found.isEmpty
              ? const _Message.assistant(
                  'I found nothing on that in Book 20. Try the name of a plant or a '
                  'condition, for example "fever" or "fennel".',
                )
              : _Message.assistant(
                  'Here is what our database holds. Best verdict: '
                  '${found.first.verdict.description}.',
                  found,
                ),
        );
      _input.clear();
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final side = sidePadding(constraints.maxWidth);
        return Column(
          children: [
            Expanded(
              child: ListView(
                controller: _scroll,
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                padding: EdgeInsets.fromLTRB(
                  side,
                  isCompact(context) ? 20 : 40,
                  side,
                  16,
                ),
                children: [
                  const PageHeader(
                    title: 'Assistant',
                    badge: 'PREVIEW',
                    lede:
                        'Ask in your own words whether a remedy holds up today.',
                  ),
                  const SizedBox(height: 14),
                  const _PreviewNotice(),
                  const SizedBox(height: 20),
                  for (final m in _messages) _Bubble(m),
                  if (_messages.length == 1) ...[
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final s in suggestions)
                          ActionChip(label: Text(s), onPressed: () => _send(s)),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                color: palette.panel,
                border: Border(top: BorderSide(color: palette.rule)),
              ),
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: EdgeInsets.fromLTRB(side, 10, side, 10),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _input,
                          textInputAction: TextInputAction.send,
                          onSubmitted: _send,
                          decoration: const InputDecoration(
                            hintText: 'e.g. Is fennel good for the eyes?',
                            isDense: true,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filled(
                        tooltip: 'Send',
                        icon: const Icon(Icons.arrow_upward),
                        onPressed: () => _send(_input.text),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _PreviewNotice extends StatelessWidget {
  const _PreviewNotice();

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: palette.panel,
        border: Border.all(color: palette.rule),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.auto_awesome_outlined, size: 20, color: palette.herb),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Coming soon: a language model connected to our evidence resolver will '
              'read your question, check it against Pliny and the modern literature, '
              'and explain the verdict. In this preview, answers come from a simple '
              'keyword match on our database. Not medical advice.',
              style: TextStyle(fontSize: 13, color: palette.muted),
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.message);

  final _Message message;

  @override
  Widget build(BuildContext context) {
    final palette = Palette.of(context);
    final user = message.fromUser;
    final bubble = Container(
      constraints: BoxConstraints(maxWidth: user ? 480 : double.infinity),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: user ? palette.herb : palette.panel,
        border: user ? null : Border.all(color: palette.rule),
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(14),
          topRight: const Radius.circular(14),
          bottomLeft: Radius.circular(user ? 14 : 4),
          bottomRight: Radius.circular(user ? 4 : 14),
        ),
      ),
      child: Text(
        message.text,
        style: TextStyle(color: user ? palette.panel : palette.ink),
      ),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: user
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        children: [
          bubble,
          for (final r in message.remedies)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: RemedyCard(r),
            ),
        ],
      ),
    );
  }
}
