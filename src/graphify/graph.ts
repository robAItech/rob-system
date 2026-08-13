/**
 * graphify/graph.ts — rezervacija imena, brez izvedbe.
 *
 * V mejniku 1 graphify NIMA ne ukaza ne dogodka ne izvedbe. Razlog je preprost:
 * v skeletu ni nicesar, kar bi rangiranje datotek uporabilo, in stub, ki vrne
 * seznam datotek, bi bil cetrti artefakt v sluzbi komponente, ki ne pocne nicesar.
 *
 * Graphify vstopi, ko bo prvi resnicni tek pokazal, da je izbira konteksta ozko grlo.
 * Preden karkoli napises, preberi Aider RepoMap: tree-sitter za simbole plus PageRank
 * nad grafom referenc je referencna izvedba te ideje in je majhna ter berljiva.
 * Novo pri nasem primeru bi bilo rangiranje glede na TRENUTNO nalogo, ne staticna
 * pomembnost simbola.
 */

export type { CodeGraph } from '../hermes/types.ts';
