# Changelog

Todas as mudanças relevantes do Nexus Nutra são registradas neste documento.

## [Não publicado]

### Documentação

- roadmap estratégico detalhado da v1.2.0 à v2.0.0;
- diagnóstico de lacunas, prioridades, dependências e critérios de entrega;
- referências de mercado, segurança, privacidade e evolução arquitetural.

## [1.1.0] — 2026-09-16 — Catálogo Inteligente

### Adicionado

- catálogo inicial com 18 alimentos brasileiros e composição por 100 g;
- busca e filtragem por categoria;
- cálculo nutricional por quantidade no navegador e no servidor;
- metas por plano e indicadores percentuais de adequação;
- alternativas alimentares da mesma categoria;
- reutilização de planos anteriores como modelo;
- visualização profissional para impressão ou PDF;
- migrações compatíveis com bancos da v1.0.0;
- testes de autorização, integridade dos cálculos e impressão.

### Melhorado

- editor de planos com busca por alimento, quantidade em gramas e origem dos dados;
- visualização do plano com metas, micronutrientes e alternativas;
- navegação profissional com acesso direto ao catálogo.

### Segurança

- valores enviados pelo navegador são ignorados quando há um alimento válido do catálogo;
- os nutrientes são recalculados no servidor para impedir adulteração do total do plano.

## [1.0.0] — 2026-09-15 — Nutrition Care Platform

- lançamento da identidade Nexus Nutra;
- painéis de nutricionista e paciente;
- planos alimentares, diário, evolução, agenda, consultas online e chat;
- proteção CSRF, controle de acesso por perfil e integração contínua.
