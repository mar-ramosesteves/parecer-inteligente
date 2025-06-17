def buscar_id(service, id_pasta_pai, nome_pasta):
    query = f"'{id_pasta_pai}' in parents and name = '{nome_pasta}' and mimeType = 'application/vnd.google-apps.folder'"
    resultado = service.files().list(q=query, fields="files(id)").execute()
    pastas = resultado.get("files", [])
    if pastas:
        return pastas[0]["id"]
    else:
        nova_pasta = {
            "name": nome_pasta,
            "parents": [id_pasta_pai],
            "mimeType": "application/vnd.google-apps.folder"
        }
        pasta_criada = service.files().create(body=nova_pasta, fields="id").execute()
        return pasta_criada["id"]
