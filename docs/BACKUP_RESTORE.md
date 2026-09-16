# Backup e restauração do Nexus Nutra

Este procedimento cobre a versão SQLite usada até a v1.7.x. Dados de saúde exigem armazenamento protegido, acesso mínimo e testes periódicos de restauração.

## Criar um backup consistente

1. Identifique o caminho definido em `DATABASE_PATH`.
2. Garanta espaço livre e acesso restrito no diretório de destino.
3. Use a API de backup do SQLite, que mantém consistência mesmo com a aplicação em execução:

```bash
sqlite3 instance/nexus_nutra.db ".backup 'backup/nexus_nutra-AAAA-MM-DD.db'"
```

4. Valide a integridade da cópia:

```bash
sqlite3 backup/nexus_nutra-AAAA-MM-DD.db "PRAGMA integrity_check;"
```

O resultado esperado é `ok`. A cópia deve ser criptografada antes de sair do servidor e nunca deve ser adicionada ao Git.

## Restaurar com segurança

1. Interrompa temporariamente a aplicação para evitar novas gravações.
2. Preserve uma cópia do banco atual.
3. Restaure o arquivo validado para um caminho novo.
4. Aponte `DATABASE_PATH` para a cópia restaurada.
5. Inicie a aplicação; as migrations pendentes serão aplicadas automaticamente.
6. Valide login, pacientes, planos e agenda antes de liberar o acesso.

## Frequência mínima recomendada

- backup diário para operação real;
- retenção definida com apoio jurídico e de segurança;
- teste mensal de restauração em ambiente isolado;
- registro da data, responsável e resultado de cada teste.

O SQLite atende ao estágio atual do produto. A v1.8.0 prevê PostgreSQL, backups automatizados, criptografia gerenciada e recuperação de desastre formal.
