// This file relates to internal XMOS infrastructure and should be ignored by external users

@Library('xmos_jenkins_shared_library@v0.53.0') _

getApproval()

pipeline {

    agent none

    parameters {
        string(
            name: 'TOOLS_VERSION_XS',
            defaultValue: '15.3.1',
            description: 'The xcore.ai (XS) XTC tools version'
        )
        string(
            name: 'XMOSDOC_VERSION',
            defaultValue: 'v8.1.2',
            description: 'The xmosdoc version'
        )
        string(
            name: 'TOOLS_VERSION_VX',
            defaultValue: '-j --repo arch_vx_slipgate -b master -a XTC 141',
            description: 'The XCORE-400 (VX) XTC tools version'
        )
        string(
            name: 'INFR_APPS_VERSION',
            defaultValue: 'v3.6.0',
            description: 'The infr_apps version'
        )
    }

    options {
        buildDiscarder(xmosDiscardBuildSettings(onlyArtifacts = false))
        skipDefaultCheckout()
        timestamps()
    }

    stages {
        stage('🏗️ Build and tests') {
            agent {
                label 'linux && 64 && documentation'
            }

            stages{
                stage('Checkout') {
                    steps {

                        println "Stage running on ${env.NODE_NAME}"

                        script {
                            def (server, user, repo) = extractFromScmUrl()
                            env.REPO_NAME = repo
                        }

                        dir(REPO_NAME){
                            checkoutScmShallow()
                        }
                    }
                }

                stage('Build XS examples') {
                    steps {
                        script {
                            // The top-level examples project also includes the VX-only
                            // MASH app. Build XS apps separately to retain their own targets.
                            ['app_fixed_clock', 'app_i2s_slave_lut', 'app_simple_lut', 'app_simple_sdm'].each { app ->
                                dir("${REPO_NAME}/examples/${app}") {
                                    xcoreBuild(
                                        toolsVersion: params.TOOLS_VERSION_XS,
                                        buildDir: 'build-xs'
                                    )
                                }
                            }
                        }
                    }
                }

                stage('Build VX examples') {
                    steps {
                        dir("${REPO_NAME}/examples/app_simple_mash") {
                            // This app selects XK-EVK-XU416 in its own CMake project.
                            xcoreBuild(
                                toolsVersion: params.TOOLS_VERSION_VX,
                                buildDir: 'build-vx'
                            )
                        }
                    }
                }

                stage('Build VX test app') {
                    steps {
                        // The MASH test app is not part of the XS pytest harness.
                        // Compile it with VX tools without claiming runtime test coverage.
                        dir("${REPO_NAME}/tests/test_mash") {
                            xcoreBuild(
                                toolsVersion: params.TOOLS_VERSION_VX,
                                buildDir: 'build-vx',
                                archiveBins: false
                            )
                        }
                    }
                }

                stage('Repo checks') {
                    steps {
                        warnError("Repo checks failed")
                        {
                            runRepoChecks("${WORKSPACE}/${REPO_NAME}")
                        }
                    }
                }

                stage('Doc build') {
                    steps {
                        dir(REPO_NAME) {
                            buildDocs()
                        }
                    }
                }

                stage('Test XS'){
                    steps {
                        dir("${REPO_NAME}/tests") {
                            // Existing pytest fixtures launch the XS test applications.
                            withTools(params.TOOLS_VERSION_XS) {
                                createVenv(reqFile: "requirements.txt")
                                withVenv {
                                    xcoreBuild(
                                        toolsVersion: params.TOOLS_VERSION_XS,
                                        buildDir: 'build-xs',
                                        archiveBins: false
                                    )
                                    sh 'pytest --junitxml=results.xml -rA -v --durations=0 -o junit_logging=all'
                                }
                                zip archive: true, zipFile: "tests.zip", dir: "bin"
                                archiveArtifacts artifacts: "bin/timing-report*.txt", allowEmptyArchive: false
                            }
                        }
                    }
                    post {
                        always {
                            junit "${REPO_NAME}/tests/results.xml"
                        }
                    }
                }

                stage('Python examples'){
                    steps {
                        dir("${REPO_NAME}/python") {
                            createVenv(reqFile: "requirements.txt")
                            withVenv {
                                dir("sw_pll") {
                                    sh 'python sw_pll_sim.py LUT'
                                    sh 'python sw_pll_sim.py SDM'
                                }
                            }
                            archiveArtifacts artifacts: "sw_pll/*.png,python/sw_pll/*.wav", allowEmptyArchive: false
                        }
                    }
                }
                stage("Archive sandbox") {
                    steps {
                        archiveSandbox(REPO_NAME)
                    }
                }
            }
            post {
                cleanup {
                    xcoreCleanSandbox()
                }
            }
        } // stage('🏗️ Build and tests')

        stage('🚀 Release') {
            when {
                expression { triggerRelease.isReleasable() }
            }
            steps {
                triggerRelease()
            }
        } // stage "Release"
    }
}
