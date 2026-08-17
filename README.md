# Chatbot IA MySQL

Rotas:
- GET /health
- POST /api/v1/tabela/criar
- POST /api/v1/tabela/popular
- GET /api/v1/tabela/{tabela}/existe
- POST /api/v1/chat

A tabela deve ser `tb_prod_[identificador]`, por exemplo `tb_prod_12345678000190-1`.
O identificador não precisa ser um CNPJ válido; o serviço apenas limita caracteres seguros e 64 caracteres.

A tabela criada precisa conter `texto_busca` para usar FULLTEXT.
