# Roadmap do Nexus Nutra

> Documento estratégico de produto e engenharia.  
> Atualizado em 23 de setembro de 2026, após a entrega da v1.5.0.

## Visão

Transformar o **Nexus Nutra** em uma plataforma brasileira de cuidado nutricional contínuo: simples para o paciente, eficiente para o nutricionista e tecnicamente preparada para clínicas, integrações e operação em produção.

O sistema deve apoiar decisões profissionais, nunca gerar diagnóstico ou prescrição clínica autônoma.

## Princípios

1. **Segurança e privacidade desde a origem** — dados de saúde recebem proteção, rastreabilidade e acesso mínimo.
2. **Profissional no controle** — cálculos e sugestões sempre passam pela validação do nutricionista.
3. **Poucos cliques** — tarefas recorrentes devem ser rápidas, reutilizáveis e fáceis de entender.
4. **Paciente engajado, não culpabilizado** — linguagem acolhedora, metas realistas e acompanhamento contextual.
5. **Evolução sustentável** — modularizar antes de escalar e medir antes de automatizar.
6. **Brasil primeiro** — português do Brasil, TACO/TBCA, LGPD e regras profissionais nacionais.

## Estado atual

| Área | Entregue até a v1.5.0 |
|---|---|
| Contas | Cadastro, login, perfis de nutricionista e paciente |
| Pacientes | Vínculo, busca, anamnese versionada, antropometria, evolução, consentimentos, anexos e relatório clínico |
| Planos | Criação, dez indicadores nutricionais, metas, alertas, revisões, modelos e impressão/PDF |
| Alimentos | Catálogo inicial TACO, alimentos personalizados, receitas, alergênicos, medidas e cálculo por quantidade |
| Acompanhamento | Diário com fotos e bem-estar, hábitos, check-ins, comentários e evolução de peso |
| Atendimento | Agenda segura, disponibilidade, bloqueios, estados, histórico, ICS, consultas online e chat |
| Segurança | CSRF, hash de senha, verificação de e-mail, recuperação segura, HTTPS para teleconsulta, bloqueio de login, expiração/revogação de sessão, consentimento e auditoria inicial |
| Experiência | PWA instalável, navegação inferior móvel, indicador de conexão e fallback offline seguro |
| Qualidade | Blueprints de autenticação, clínica e nutrição, migrations numeradas, 24 testes, Ruff e GitHub Actions |

## Diagnóstico de lacunas

| Prioridade | Lacuna | Impacto |
|---|---|---|
| P0 | Falta autenticação multifator e gestão centralizada de dispositivos | Risco residual de segurança |
| P0 | Auditoria e consentimento existem em nível inicial, mas faltam política de retenção e exportação/exclusão de dados | Impede uso responsável com dados sensíveis |
| P0 | SQLite e aplicação monolítica atendem ao MVP, mas limitam concorrência e crescimento | Risco operacional futuro |
| P1 | Lembretes da agenda ainda são internos e não possuem entrega por e-mail, WhatsApp ou push | Menor alcance das automações |
| P1 | Falta política operacional de retenção, exportação e exclusão do prontuário | Governança clínica ainda incompleta |
| P1 | Catálogo ainda não possui importação controlada TACO/TBCA, sinônimos ou fontes versionadas | Cobertura e rastreabilidade nutricional ainda são limitadas |
| P1 | Diário ainda não registra atividade física nem oferece análise consolidada versus metas do plano | Contexto longitudinal ainda incompleto |
| P2 | Não há equipe, unidades, permissões granulares, financeiro ou indicadores da clínica | Limita operação multiprofissional |
| P2 | Não há notificações push, API pública ou integração com calendários e wearables | Experiência ainda parcialmente desconectada |
| P3 | Não há multiempresa, planos comerciais, cobrança recorrente ou personalização por clínica | Ainda não opera como SaaS |

## Sequência recomendada

~~~mermaid
flowchart TD
    A["v1.2 · Agenda Segura ✅"] --> S["v1.2.1 · Identidade Segura ✅"]
    S --> B["v1.3 · Prontuário Clínico ✅"]
    B --> C["v1.4 · Inteligência Nutricional ✅"]
    C --> D["v1.5 · Engajamento PWA ✅"]
    D --> E["v1.6 · Gestão de Clínicas"]
    E --> F["v1.7 · Integrações"]
    F --> G["v1.8 · Produção e Escala"]
    G --> H["v2.0 · Plataforma SaaS"]
~~~

Segurança, acessibilidade, testes e privacidade são trilhas contínuas e fazem parte da definição de pronto de todas as versões.

## Roadmap versionado

### v1.2.0 — Agenda Segura e Automações

**Status:** entregue em 16 de setembro de 2026. Recuperação de senha e verificação de e-mail foram separadas para a v1.2.1, pois dependem do canal transacional de e-mail.

**Objetivo:** reduzir faltas, organizar horários e criar a fundação de segurança necessária para os próximos módulos clínicos.

#### Produto

- disponibilidade semanal do nutricionista;
- criação de bloqueios, intervalos e duração padrão;
- estados: agendada, confirmada, concluída, cancelada e não compareceu;
- confirmação, cancelamento e reagendamento com registro de motivo;
- lembretes internos configuráveis;
- exportação de compromisso em formato ICS;
- painel “Hoje” com consultas e pendências;
- histórico de alterações da consulta.

#### Segurança e plataforma

- recuperação de senha por token de uso único;
- verificação de e-mail;
- bloqueio progressivo de tentativas de login;
- expiração e revogação de sessões;
- trilha inicial de auditoria;
- consentimento e aceite de política de privacidade versionados;
- migrations numeradas, substituindo alterações ad hoc;
- divisão das rotas em blueprints por domínio.

#### Definição de pronto

- testes de autorização e transição de estados;
- nenhuma URL de consulta aceita fora de HTTPS em produção;
- ações sensíveis registradas na auditoria;
- documentação de backup e restauração;
- fluxo responsivo para nutricionista e paciente.

**Complexidade:** alta · **Prioridade:** P0/P1

---

### v1.2.1 — Identidade Segura

**Objetivo:** concluir a segurança de contas com fluxos verificáveis e comunicação transacional.

**Status:** entregue em 16 de setembro de 2026.

#### Entregas

- recuperação de senha com token de uso único, expiração e revogação;
- verificação de e-mail e reenvio controlado;
- adaptador SMTP configurável sem segredos no repositório;
- registro de eventos de identidade na auditoria;
- testes de enumeração de conta, expiração e reutilização de token;
- separação inicial das rotas de autenticação e agenda em blueprints.

**Complexidade:** média · **Prioridade:** P0

---

### v1.3.0 — Prontuário e Avaliação Nutricional

**Objetivo:** centralizar a avaliação clínica e permitir acompanhamento longitudinal estruturado.

**Status:** entregue em 22 de setembro de 2026.

#### Entregas

- anamnese configurável por seções;
- histórico clínico, familiar, alimentar e de atividade;
- alergias, intolerâncias, preferências e restrições;
- medicamentos e suplementos;
- sinais, sintomas, sono, ingestão de água e funcionamento intestinal;
- avaliação antropométrica com peso, altura, IMC, circunferências e composição corporal;
- metas clínicas com histórico e responsável;
- notas de evolução com autoria e data;
- comparação entre avaliações;
- relatório clínico em PDF;
- anexos com tipo, tamanho e acesso controlados;
- consentimentos específicos por finalidade.

#### Definição de pronto

- histórico não pode ser sobrescrito sem rastreabilidade;
- campos sensíveis possuem controle de acesso;
- cálculos exibem fórmula, unidade e limitações;
- relatórios identificam profissional, paciente e data;
- cobertura de testes dos cálculos e permissões.

**Complexidade:** alta · **Prioridade:** P1

---

### v1.4.0 — Inteligência Nutricional Brasileira

**Status:** entregue em 22 de setembro de 2026. Importação TACO/TBCA, sinônimos, análise do diário e relatórios de ingestão seguem priorizados como extensões futuras.

**Objetivo:** tornar a prescrição rápida, verificável e flexível sem automatizar a decisão clínica.

#### Entregas

- alimentos e medidas caseiras personalizados pelo profissional;
- receitas com ingredientes, rendimento e porções;
- cálculo de receitas e preparações no servidor;
- energia, macronutrientes, fibras, cálcio, ferro, gordura saturada, sódio e açúcares;
- catálogo profissional isolado por nutricionista;
- alertas de alergênicos e conflitos com restrições cadastradas;
- versionamento de planos publicados;
- biblioteca original de ícones SVG e identidade visual renovada.

#### Definição de pronto

- alterações em alimentos não modificam retroativamente planos publicados;
- arredondamentos e unidades são testados;
- alertas são apresentados como apoio e exigem confirmação profissional;
- receitas e alimentos particulares respeitam a propriedade do nutricionista.

**Complexidade:** alta · **Prioridade:** P1

---

### v1.5.0 — Jornada do Paciente e PWA

**Status:** entregue em 23 de setembro de 2026. Notificações push, lembretes externos e rascunhos offline permanecem no backlog porque exigem consentimento, filas e política de sincronização.

**Objetivo:** aumentar adesão e facilitar registros no celular sem exigir aplicativo nativo.

#### Entregas

- Progressive Web App instalável;
- modo responsivo refinado e navegação inferior no celular;
- diário com foto, humor, fome, saciedade, sintomas e observações;
- metas de hábitos configuráveis;
- comentários do nutricionista nos registros;
- check-in semanal;
- painel de adesão com tendências, sem linguagem punitiva;
- fallback offline para o shell público, sem cache de dados de saúde;
- indicador de conectividade e fluxo de instalação;
- ícone próprio e atalhos do aplicativo.

#### Definição de pronto

- páginas autenticadas e dados clínicos não são persistidos pelo service worker;
- fotos são validadas e servidas apenas a usuários autorizados;
- criação de hábitos e comentários profissionais são auditados;
- fluxos de jornada possuem cobertura automatizada.

**Complexidade:** média/alta · **Prioridade:** P1/P2

---

### v1.6.0 — Gestão de Clínicas

**Objetivo:** permitir que consultórios e clínicas gerenciem equipe, operação e resultados.

#### Entregas

- organizações, unidades e múltiplos profissionais;
- papéis: administrador, nutricionista, recepção e financeiro;
- permissões granulares por ação;
- agenda compartilhada por profissional e unidade;
- cadastro de serviços, pacotes e duração;
- cobranças, recibos e controle de pagamentos;
- suporte inicial a Pix por provedor homologado;
- despesas e fluxo de caixa básico;
- indicadores de consultas, faltas, retenção e receita;
- identidade visual da clínica;
- convites e desativação de colaboradores;
- exportação administrativa.

#### Definição de pronto

- isolamento rigoroso entre organizações;
- recepção não acessa conteúdo clínico sem permissão;
- valores monetários usam tipo e arredondamento adequados;
- ações administrativas críticas entram na auditoria.

**Complexidade:** muito alta · **Prioridade:** P2

---

### v1.7.0 — Integrações e API

**Objetivo:** conectar o Nexus Nutra ao ecossistema usado por profissionais e pacientes.

#### Entregas

- API REST versionada e documentada;
- tokens com escopos e revogação;
- webhooks assinados;
- Google Calendar e Microsoft Outlook;
- Google Meet, Zoom ou Microsoft Teams;
- importação/exportação CSV;
- integração gradual com dados de atividade e saúde, mediante consentimento;
- arquitetura preparada para padrões de interoperabilidade em saúde;
- central de integrações com status e logs;
- filas para sincronizações e tentativas automáticas.

#### Definição de pronto

- nenhuma integração recebe mais dados que o necessário;
- tokens e segredos não são armazenados em texto puro;
- webhooks são idempotentes;
- falhas externas não bloqueiam a aplicação principal.

**Complexidade:** muito alta · **Prioridade:** P2

---

### v1.8.0 — Produção, Observabilidade e Escala

**Objetivo:** preparar operação confiável com usuários reais e crescimento controlado.

#### Entregas

- PostgreSQL como banco principal;
- cache e filas de tarefas;
- armazenamento de anexos compatível com objetos;
- execução em contêiner;
- ambientes separados de desenvolvimento, homologação e produção;
- logs estruturados, métricas, tracing e alertas;
- backups criptografados e testes de restauração;
- política de retenção e descarte;
- análise de dependências e imagens;
- testes de carga, concorrência e recuperação;
- objetivos de disponibilidade e resposta a incidentes;
- documentação operacional.

#### Definição de pronto

- restauração comprovada em ambiente isolado;
- migração sem perda de dados;
- segredos fora do repositório;
- alertas acionáveis para indisponibilidade e erros;
- checklist formal de produção aprovado.

**Complexidade:** muito alta · **Prioridade:** P0 antes da comercialização

---

### v2.0.0 — Nexus Nutra Platform

**Objetivo:** consolidar o produto como plataforma SaaS para profissionais e clínicas.

#### Entregas

- multiempresa maduro;
- planos de assinatura e limites por produto;
- cobrança recorrente;
- onboarding guiado;
- configuração por clínica;
- marca personalizada;
- painel executivo;
- central de suporte e status;
- gestão de termos, privacidade e solicitações do titular;
- ecossistema de integrações;
- arquitetura preparada para aplicativo nativo, caso métricas justifiquem.

**Complexidade:** muito alta · **Prioridade:** P3

## Melhorias transversais

### Segurança e privacidade

- autenticação multifator opcional;
- rotação e gestão de segredos;
- Content Security Policy;
- criptografia de dados sensíveis;
- revisão de dependências;
- inventário de dados e bases legais;
- portal de solicitações do titular;
- exportação, correção e exclusão conforme política definida;
- plano de resposta a incidentes.

### Qualidade de engenharia

- cobertura de testes por domínio;
- testes de navegador para jornadas críticas;
- type checking;
- migrations versionadas;
- arquitetura em camadas: rotas, serviços, repositórios e domínio;
- ambiente de homologação;
- revisão automática de segurança;
- documentação de decisões arquiteturais.

### Experiência

- design system com tokens e componentes;
- ícones consistentes no lugar de caracteres decorativos;
- estados de carregamento, vazio, erro e sucesso;
- acessibilidade WCAG como critério de entrega;
- atalhos de teclado no painel profissional;
- pesquisa global;
- central de ajuda contextual.

### Produto e métricas

- ativação: primeiro paciente, primeiro plano e primeira consulta;
- tempo médio para montar um plano;
- adesão ao diário;
- comparecimento às consultas;
- retenção de profissionais e pacientes;
- métricas sem registrar conteúdo clínico sensível em analytics.

## Backlog priorizado

### Fazer agora

1. iniciar organizações, unidades e RBAC da v1.6.0;
2. criar testes de navegador das jornadas críticas;
3. definir retenção, exportação e exclusão de dados;
4. ampliar o catálogo com importação controlada e fontes versionadas;
5. analisar diário alimentar versus metas do plano.

### Fazer em seguida

1. equipes, unidades e permissões granulares;
2. agenda compartilhada e indicadores operacionais;
3. notificações consentidas e lembretes externos;
4. relatórios de ingestão em PDF e CSV;
5. importação TACO/TBCA controlada e versionada.

### Adiar até existir base operacional

1. inteligência artificial generativa;
2. prescrição automática;
3. aplicativo nativo separado;
4. marketplace;
5. faturamento de convênios;
6. recomendações baseadas em wearables sem validação clínica;
7. multiempresa antes de PostgreSQL, auditoria e RBAC.

## Referências de mercado

O roadmap considera padrões observados em plataformas consolidadas, sem copiar identidade visual ou fluxos proprietários:

- [Nutrium](https://nutrium.com/) — planos, agendamento, acompanhamento e aplicativo do paciente;
- [Healthie](https://www.gethealthie.com/nutrition) — prontuário, teleatendimento, formulários, diário e operação da clínica;
- [Practice Better](https://practicebetter.io/who-we-serve/nutritionists) — automações, programas, pagamentos e gestão da prática;
- [Cronometer Pro](https://cronometer.com/pro/) — metas, análise detalhada, receitas, relatórios e base alimentar verificada.

## Referências regulatórias

- [Conselho Federal de Nutricionistas](https://cfn.org.br/) — normas profissionais e telenutrição;
- [Autoridade Nacional de Proteção de Dados](https://www.gov.br/anpd/) — orientações de proteção de dados e LGPD.

Este documento é um plano técnico e não substitui avaliação jurídica, regulatória ou clínica antes da disponibilização comercial.
