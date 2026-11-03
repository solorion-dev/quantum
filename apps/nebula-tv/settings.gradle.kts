// NebulaTV — leanback Android TV client for Nebula.
// Self-contained Gradle build; intentionally NOT wired into any Node/pnpm
// workspace tooling (native Android stack — see docs/MONOREPO.md
// stack-affinity guardrail).
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "nebula-tv"
include(":app")
