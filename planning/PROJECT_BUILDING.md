# OBJECTIVE

Checklist que ajuda a estruturar o desenvolvimento via arquitetura de projetos com IA para tornar eficazes os outputs.

**Não mexa nesse checklist**. Ele é para humanos acompanharem o projeto.


## Glossário

a - anulado
f - Revisão Futura
x - concluído
n - Não se aplica
r - Rollback - falhou

## Fases

[X] - Escreva em CLAUDE: Não faça alterações em PROJECT_BULDING.md. As fases e controles de progresso deve ser feitos e registrados em PLAN.md. - **Não faça alterações** em `planning/PROJECT_BUILDING.md`. Todas as decisões vivem em `planning/PLAN.MD`
[X] - Construir pasta planning E criar arquivo PLAN.md
[x] - Escrever no CLAUDE.md que toda a documentação estará em `planning` directory e o key document is PLAN.md
[n] - Criar uma pesquisa do plano equivalente ao texto abaixo:
    - "Realize uma pesquisa abrangente(...) e escreva documentos no diretório de planejamento em XXX_API.md"
    - "Pesquise API. Escreva a documentação com exemplos de código"
    - "Use isso para projetar a API em Python que deve ser usada para XXXX. Documente isso em XXX.md"
    - Por fim, documente a estrutura de código para [OBJETIVO]
[n] - Criar novo arquivo com a estrutura do backend em detalhes, com code snippets mais exemplo, de todas funcionalidades, escreva tudo em XXX_BACKEND.md
[ ] - Subplanos dentro do plano para cada grande marco de implementação com certificação de bons testes em cada subplano
[x] - .claude/agents está na pasta do projeto
[x] - Prepara o Github
[x] - Preparar o gitignore
[x] - Crie a pasta bug_fix
[x] - Confirmar Skills para planejar as fases e subfases. GSD, feature-dev e superpowers são bons exemplos
[x] - Adicionar BEHVIORAL_GUIDELINES à pasta do projeto e no claude.
[n] - Após o /init - Leia todo o conteúdo de planning/. Depois, escreva o planning/ADVERSARIAL_REVIEW.md, que testa as falhas e ambiguidades do script: "Aja como um adversário maximamente competente. Sua tarefa é encontrar todas as ambiguidades, lacunas semânticas e formulações suaves neste documento que permiritiram a você seguir tecnicamente a refra enquanto viala seu espírito. Liste cada brecha com o caminho de exploração específico".
[n'] - Solicitar que desenvolvimento do site seja feito em pequenas partes para facilitar o teste humano.
[ ] - Mapa de testes (o que teste e como testar) escrito em um arquivo TESTES.md. Explica o teste de cada fase caso queira repetir. 
[n] - Comparar arquitetura atual e clean Architecture
[n] - Avaliar usar sandbox e WSL2/VSCODE Ubuntu para execução
[ ] - Criar e instalar dependências
[n] - Governança de desenvolvimento - Explica critérios de sucesso de cada fase em `definition of done.md` para humanos poderem acompanhar.
[n] - sinalizar quais arquivos da NÃO SÃO entradas (raiz, scripts antigos, minhas_notas.ignore)
[x] - Criar a pasta script_antigos e informar ao claude para ignorar a pasta
[x] - Clonar o repositório do thariq https://github.com/ThariqS/html-effectiveness. Crie um html de [tarefa] inspirados nos modelos disponíveis em html-effectveness/ para aumentar minha compreensão das suas atividades e a eficiência das minhas decisões.
[n] - AI Operational assistant prompt - Atue como a personalidade  do documento com o qual estou interagindo. Seu nome é "Assistente de IA". Usando o contexto fornecido, responda à pergunta do usuário da melhor forma possível utilizando os recursos disponibilizados.
[x] - No Claude.md - Convenção de documentação do código - "Toda função com docstring explicando, nesta ordem: por que a função existe (o problema que ela resolve / o motivo de ser função separada); a lógica do input ao output, em fases numeradas (Entrada → Fase 1 → Fase 2 → … → Saída), descrevendo o que cada bloco transforma. Além disso, toda linha de código comentada — inclusive as que parecem óbvias."
[n] - Se não houver nada no contexto relevante para a pergunta em questão, apenas diga "Hmm, não tenho certeza" e pare por aí. Recuse-se a responder qualquer pergunta que não seja sobre essas informações. Nunca saia do personagem.
[N] No Claude.md - always include e2e tests to cover important paths. You should always make sure that the plans include a test suite that covers the happy paths and edge cases. Your tests should be high quality and give confidence while covering most of the implementation.
[N] - Reproduzir o site atual como um mock não-funcional (cópia React/Vite, dados, hardcoded) para servir de base/canvas no desenho/design de uma futura nova página. A nova página (que conectará a esta, herdará os estilos e compartilhará o mesmo BD).

### Python env
1 - powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
2 - .venv\Scripts\activate

### Requirements
4 - uv pip install ....
5 - uv pip freeze > requirements.txt