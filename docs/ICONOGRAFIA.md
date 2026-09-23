# Nexus Line — Nexus Nutra

O Nexus Nutra usa a família visual **Nexus Line**, compartilhada pelo ecossistema Nexus. A linguagem comum facilita o reconhecimento entre produtos sem apagar a finalidade de cada sistema.

## Contrato visual

| Propriedade | Padrão |
|---|---|
| Grade | `24 × 24` |
| Traço | `1.75` |
| Terminações e junções | arredondadas |
| Cor na interface | `currentColor` |
| Preenchimento | nenhum, salvo exceção documentada da marca |
| Formato | SVG local, sem fonte ou CDN externa |

Ícones de interface são monocromáticos e herdam a cor do contexto. Gradientes ficam reservados para a logomarca e o ícone do aplicativo. Toda ação sem texto deve ter um nome acessível (`aria-label`); símbolos decorativos permanecem ocultos de tecnologias assistivas.

## Identidade do produto

- verde principal: `#197A50`;
- verde de evolução: `#76C043`;
- superfície suave: `#F5F8F6`;
- vocabulário próprio: alimentação, clínica, jornada, hidratação, medidas, diário, receitas e bem-estar.

O sprite [`static/img/nexus-icons.svg`](../static/img/nexus-icons.svg) contém 38 símbolos autorais. Seus metadados e categorias ficam em [`static/img/nexus-icons-manifest.json`](../static/img/nexus-icons-manifest.json).

## Uso em templates

```jinja2
{% from "_icons.html" import icon %}
{{ icon("food") }}
```

O macro produz um SVG decorativo. Para botões exclusivamente visuais, o elemento interativo deve receber `aria-label`.

## Ecossistema Nexus

| Produto | Papel visual | Cor principal | Vocabulário específico |
|---|---|---|---|
| Nexus ERP | base corporativa e semântica comum | `#66428A` | vendas, estoque, fiscal, financeiro e RH |
| Nexus Nutra | cuidado nutricional e evolução | `#197A50` | alimento, plano, medidas, diário e hábitos |
| Nexus Core | inteligência local e segurança | `#722F37` | agentes, modelos, memória, voz e runtime |
| Nexus ADV | identidade jurídica reservada | `#8B1E2D` + `#C6A15B` | processos, prazos, contratos e jurisprudência |

Novos ícones devem reutilizar a semântica comum quando ela existir. Um símbolo específico só entra no produto cuja atividade o justifica.
