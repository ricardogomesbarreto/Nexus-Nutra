# Changelog

Todas as mudanças relevantes do Nexus Nutra são registradas neste documento.

## [Não publicado]

### Planejado

- recuperação de senha por token de uso único e verificação de e-mail;
- separação progressiva das rotas por domínio;
- testes de navegador para os fluxos críticos da agenda.

## [1.2.0] — 2026-09-16 — Agenda Segura

### Adicionado

- disponibilidade semanal e períodos de bloqueio do nutricionista;
- duração padrão e lembretes internos configuráveis por consulta;
- estados agendada, confirmada, concluída, cancelada e não compareceu;
- confirmação, cancelamento e reagendamento com justificativa;
- histórico de eventos por consulta e trilha inicial de auditoria;
- exportação de compromissos no formato ICS;
- painel profissional “Hoje” e resumo operacional da agenda;
- consentimento de privacidade versionado no cadastro;
- migrations numeradas com registro em `schema_migrations`;
- documentação de backup e restauração do SQLite;
- cinco cenários automatizados para agenda, migrations, auditoria e autenticação.

### Segurança

- detecção de conflito entre consultas e bloqueios de horário;
- links de consulta online aceitos somente com HTTPS;
- bloqueio temporário após cinco tentativas inválidas de login;
- sessões com expiração de 12 horas e revogação de outros dispositivos;
- regras de autorização e transições válidas para alterações de consulta.

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
