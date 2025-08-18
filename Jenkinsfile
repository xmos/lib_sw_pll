// This file relates to internal XMOS infrastructure and should be ignored by external users

@Library('xmos_jenkins_shared_library@v0.41.2') _

getApproval()

pipeline {

    agent none

    parameters {
        string(
            name: 'TOOLS_VERSION',
            defaultValue: '15.3.1',
            description: 'The XTC tools version'
        )
        string(
            name: 'XMOSDOC_VERSION',
            defaultValue: 'v7.0.0',
            description: 'The xmosdoc version'
        )
        string(
            name: 'INFR_APPS_VERSION',
            defaultValue: 'v2.0.1',
            description: 'The infr_apps version'
        )
        choice(
            name: 'TEST_LEVEL', choices: ['smoke', 'default', 'extended'],
            description: 'The level of test coverage to run'
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

                stage('Examples build') {
                    steps {
                        dir("${REPO_NAME}/examples") {
                            xcoreBuild()
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

                stage('Test'){
                    steps {
                        dir("${REPO_NAME}/tests") {
                            withTools(params.TOOLS_VERSION) {
                                createVenv(reqFile: "requirements.txt")
                                withVenv {
                                    xcoreBuild(archiveBins: false)
                                    sh 'pytest --junitxml=results.xml -rA -v --durations=0 -o junit_logging=all'
                                }
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
            steps {
                triggerRelease()
            }
        }
    }
}
