# Changelog

Todas as mudanças relevantes do Nexus Nutra são registradas neste documento.

## [Não publicado]

### Planejado

- organizações, unidades, equipe e permissões granulares;
- notificações consentidas e lembretes externos;
- testes de navegador para os fluxos críticos de identidade e agenda.

## [1.5.0] — 2026-09-23 — Jornada do Paciente e PWA

### Adicionado

- Progressive Web App instalável com manifesto, ícone autoral e atalhos;
- service worker limitado ao shell público, com fallback offline seguro;
- navegação inferior para as principais tarefas no celular;
- diário alimentar com foto, humor, saciedade, hidratação e sintomas;
- check-in semanal de energia, sono, confiança, avanços e dificuldades;
- metas de hábitos criadas pelo nutricionista e registradas pelo paciente;
- comentários profissionais vinculados às refeições;
- painel de jornada e resumo semanal no painel do paciente;
- migration v6 e três novos cenários, elevando a suíte para 24 testes.

### Segurança e privacidade

- fotos recebem nomes internos aleatórios e validação de extensão, assinatura e tamanho;
- acesso às fotos é restrito ao paciente e ao nutricionista vinculado;
- respostas profissionais e criação de hábitos são auditadas;
- o service worker não armazena páginas autenticadas nem conteúdo clínico;
- respostas de imagens privadas usam `Cache-Control: private, no-store`.

## [1.4.0] — 2026-09-22 — Inteligência Nutricional Brasileira

### Adicionado

- ambiente profissional para cadastrar alimentos personalizados e receitas;
- cálculo de receitas no servidor a partir de ingredientes, rendimento e dez indicadores nutricionais;
- sódio, gordura saturada e açúcares no catálogo, nas metas, nos planos e nos relatórios;
- alertas de alergênicos confrontados com alergias, intolerâncias e restrições da anamnese;
- versões numeradas e histórico de revisão dos planos alimentares;
- catálogo isolado por nutricionista, mantendo os alimentos globais disponíveis;
- biblioteca original de ícones vetoriais para toda a interface;
- logomarca com transparência aplicada ao produto, documentos e README;
- blueprint nutricional e migration v5 compatível com bancos existentes;
- três novos cenários automatizados, elevando a suíte para 21 testes.

### Segurança e integridade

- nutrientes e alergênicos das receitas são recalculados no servidor;
- alimentos particulares só podem ser usados pelo profissional proprietário;
- planos publicados preservam cópias dos nutrientes de cada item;
- alertas clínicos são reapresentados no detalhe do plano para revisão profissional.

## [1.3.0] — 2026-09-22 — Prontuário Clínico

### Adicionado

- anamnese estruturada com versões imutáveis e autoria;
- histórico clínico, familiar, alimentar, de atividade, alergias e restrições;
- registro de medicamentos, suplementos, sintomas, sono, água e hábito intestinal;
- avaliações antropométricas longitudinais com composição corporal e circunferências;
- cálculo no servidor de IMC e relação cintura–quadril, com fórmulas e limitações visíveis;
- notas de evolução, metas clínicas e observações com linha do tempo;
- eventos versionados de consentimento por finalidade;
- anexos PDF, JPG e PNG de até 5 MB, validados por extensão, MIME e assinatura;
- relatório clínico profissional pronto para impressão ou PDF;
- migration v4 e blueprint clínico dedicado;
- três novos cenários automatizados, elevando a suíte para 18 testes.

### Segurança

- acesso ao prontuário, relatório e anexos restrito ao nutricionista vinculado;
- nomes internos aleatórios para anexos e downloads mediados pela aplicação;
- histórico clínico preservado sem atualização destrutiva;
- trilha de auditoria para anamnese, avaliação, nota, consentimento e anexo;
- valores antropométricos derivados são recalculados no servidor.

## [1.2.1] — 2026-09-16 — Identidade Segura

### Adicionado

- confirmação de e-mail com link de uso único e validade de 24 horas;
- reenvio controlado de confirmação sem enumeração de contas;
- recuperação de senha com link de uso único e validade de 30 minutos;
- adaptador SMTP configurável com TLS, SSL e autenticação opcional;
- outbox isolado para testes e desenvolvimento sem envio externo;
- migration v3 para tokens de identidade e compatibilidade de contas existentes;
- páginas profissionais para confirmação, recuperação, redefinição e links expirados;
- auditoria dos eventos críticos de identidade;
- três cenários de segurança, elevando a suíte para 15 testes.

### Segurança

- somente hashes SHA-256 dos tokens são persistidos no banco;
- emissão de novo token invalida os anteriores da mesma finalidade;
- redefinição de senha revoga sessões existentes e libera bloqueios de login;
- respostas de recuperação e reenvio não confirmam a existência de uma conta;
- limitação de três solicitações por finalidade em uma hora;
- contas criadas antes da v1.2.1 são migradas como verificadas, sem bloquear usuários existentes.

### Arquitetura

- rotas de cadastro, login e identidade extraídas para o blueprint `auth`;
- configuração de e-mail centralizada e sem segredos versionados.

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
