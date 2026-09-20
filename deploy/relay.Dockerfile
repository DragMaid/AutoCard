# The C# relay. Build context is the repository root so this file can sit beside
# the other two, but nothing outside server/ is used.
#
#   docker build -f deploy/relay.Dockerfile -t autocard-relay .

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build

WORKDIR /src
COPY server/AutoCard.Server/AutoCard.Server.csproj AutoCard.Server/
RUN dotnet restore AutoCard.Server/AutoCard.Server.csproj

COPY server/AutoCard.Server/ AutoCard.Server/
RUN dotnet publish AutoCard.Server/AutoCard.Server.csproj \
    -c Release -o /app --no-restore


FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime

ENV ASPNETCORE_ENVIRONMENT=Production \
    DOTNET_gcServer=1

WORKDIR /app
COPY --from=build /app ./

USER $APP_UID

EXPOSE 8080
ENTRYPOINT ["dotnet", "AutoCard.Server.dll"]
