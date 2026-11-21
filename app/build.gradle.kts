plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "ma.pharmagarde.marrakech"
    compileSdk = 36

    defaultConfig {
        applicationId = "ma.pharmagarde.marrakech"
        minSdk = 26
        // Google Play كيفرض target API جديد كل عام. شوف المطلوب فـ Play Console قبل النشر.
        targetSdk = 36
        // كل بناء ديال release كياخد رقم أكبر أوتوماتيك (Google Play كيطلب versionCode يزيد فكل نسخة).
        versionCode = (System.getenv("GITHUB_RUN_NUMBER")?.toIntOrNull() ?: 1) + 100
        versionName = "1.0"
    }

    signingConfigs {
        create("release") {
            val path = System.getenv("KEYSTORE_PATH")
            if (path != null) {
                storeFile = file(path)
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KEY_ALIAS")
                keyPassword = System.getenv("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            // ما كنقلصوش الكود: التطبيق صغير، وهكا كنتفاداو شي خطأ ما كيبانش غير فنسخة release.
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release").takeIf { System.getenv("KEYSTORE_PATH") != null }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.13.1")
}
