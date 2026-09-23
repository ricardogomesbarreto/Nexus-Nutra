# Política de segurança

O Nexus Nutra processa informações pessoais e pode processar dados de saúde. Esses
dados exigem controles técnicos, operacionais e jurídicos proporcionais ao risco.

## Versões suportadas

| Versão | Suporte |
|---|---|
| 1.5.x | Correções de segurança |
| anteriores | Não suportadas |

## Relato responsável

Não publique vulnerabilidades, dados pessoais, tokens ou credenciais em issues.
Entre em contato de forma privada com o mantenedor e informe versão, impacto,
passos mínimos para reprodução e evidências sem dados reais. O canal privado deve
ser configurado antes do lançamento público.

## Controles atuais

- hash de senha `scrypt` pelo Werkzeug e mínimo de 12 caracteres;
- CSRF em operações de escrita e comparação de token em tempo constante;
- cookies seguros em produção e sessões absolutas de oito horas;
- bloqueio progressivo de tentativas de login e revogação de sessões;
- confirmação de e-mail e recuperação com token aleatório, hash e uso único;
- autorização por vínculo entre profissional e paciente;
- anexos privados com validação de tipo, assinatura e tamanho;
- auditoria das principais ações clínicas, de agenda e identidade;
- CSP, HSTS, anti-framing, validação de host e respostas privadas sem cache;
- PWA sem cache de páginas autenticadas ou conteúdo clínico.

## Limites conhecidos da v1.5.1

- o runtime ainda usa SQLite e não está aprovado para operação clínica pública;
- MFA, criptografia de campos e gestão central de dispositivos ainda não existem;
- retenção, exportação e descarte dependem de política operacional aprovada;
- segurança não equivale a conformidade automática com LGPD ou normas clínicas.

## Regras de produção

Produção exige Hostinger VPS endurecida, HTTPS, PostgreSQL em rede privada,
segredos fora do Git, backups criptografados, restauração testada, logs sem dados
clínicos e revisão independente antes do lançamento. Veja
[`docs/PRODUCTION_ARCHITECTURE.md`](docs/PRODUCTION_ARCHITECTURE.md).

